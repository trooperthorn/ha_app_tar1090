const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async()=>{
 const port=18765;
 const server=spawn(process.env.PYTHON || 'python',['-m','http.server',String(port),'--bind','127.0.0.1','--directory',process.argv[2]||'work/web']);
 const launch = process.env.CHROME ? {executablePath:process.env.CHROME} : {};
 let browser;
 try {
  await new Promise(r=>setTimeout(r,1000));
  browser=await chromium.launch({headless:true,...launch});
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[], missing=[], external=[];
  page.on('pageerror',e=>errors.push(e.stack));
  page.on('response',r=>{if(r.status()>=400)missing.push([r.status(),r.url()]);});
  let state='live',epoch='test1',sequence=1;
  const stamp=Date.now()/1000;
  const status=()=>({state,epoch,sequence,age_seconds:state==='expired'?70:0,upstream_encoding:'gzip',average_body_bits_per_second:100,expire_seconds:60});
  const fixture={now:stamp,messages:1000,aircraft:[
   {hex:'a12345',flight:'TEST123 ',lat:37.01,lon:-122.01,alt_baro:4500,gs:150,track:90,seen:0,seen_pos:0,messages:100,type:'adsb_icao'},
   {hex:'b12345',flight:'HIGH123 ',lat:37.02,lon:-122.02,alt_baro:20000,gs:250,track:130,seen:0,seen_pos:0,messages:100,type:'adsb_icao'}]};
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(url.hostname!=='127.0.0.1'){external.push(url.href);return route.abort();}
   const prefix='/api/hassio_ingress/test/';
   const p=url.pathname.startsWith(prefix)?'/'+url.pathname.slice(prefix.length):url.pathname;
   let value;
   if(p.endsWith('/config.js')) return route.fulfill({contentType:'text/javascript',body:"MapType_tar1090='blank'; showPictures=false; planespottersAPI=false; useRouteAPI=false; routeApiUrl='';"});
   if(p.endsWith('/data/receiver.json'))value={lat:37,lon:-122,refresh:2000,history:0,version:'mock',binCraft:false,zstd:false,dbServer:false};
   if(p.endsWith('/chunks/chunks.json'))value={chunks:[],chunks_all:[]};
   if(p.endsWith('/data/aircraft.json'))value={...fixture,ha_bridge:status()};
   if(p.endsWith('/status.json'))value=status();
   if(p.endsWith('/upintheair.json'))value={rings:[]};
   if(value)return route.fulfill({contentType:'application/json',body:JSON.stringify(value)});
   if(p.includes('/db-current/')) {
    const local=path.join(process.argv[2]||'work/web',p.slice(1));
    if(fs.existsSync(local))return route.fulfill({contentType:'application/json',body:require('node:zlib').gunzipSync(fs.readFileSync(local))});
   }
   return route.continue({url:`http://127.0.0.1:${port}${p}${url.search}`});
  });
  const query='zoom=9&hideButtons&hideSideBar&centerReceiver&mapDim=0.4&iconScale=0.7&labelScale=0.75&extendedLabels=2&rangeRings=0&filterAltMax=10000&mapOrientation=150&enableLabels';
  await page.goto(`http://127.0.0.1:${port}/api/hassio_ingress/test/?${query}`);
  await page.waitForFunction(()=>typeof loadFinished!=='undefined'&&loadFinished,null,{timeout:15000}).catch(async error=>{console.log(JSON.stringify({errors,missing,external,body:(await page.locator('body').innerText()).slice(-1500)}));throw error;});
  await page.waitForTimeout(5000);
  const inspect=await page.evaluate(()=>({planes:Object.keys(g.planes),zoom:OLMap.getView().getZoom(),angle:g.mapOrientation,labels:g.extendedLabels,alt:PlaneFilter.maxAltitude}));
  assert.ok(inspect.planes.includes('a12345'),JSON.stringify(inspect));
  assert.equal(inspect.alt,10000);
  assert.equal(inspect.labels,2);
  await page.screenshot({path:'work/map-live.png'});
  state='expired';
  await page.waitForTimeout(3000);
  assert.equal(await page.evaluate(()=>Object.keys(g.planes).length),0,'expired aircraft must be removed');
  await page.screenshot({path:'work/map-expired.png'});
  state='live';sequence++;fixture.now+=1;
  await page.waitForTimeout(5000);
  assert.ok(await page.evaluate(()=>Object.keys(g.planes).length>0),'recovery');
  epoch='test2';fixture.now-=20;
  await page.waitForTimeout(5000);
  assert.ok(await page.evaluate(()=>Object.keys(g.planes).length>0),'source clock reset recovery');
  assert.deepEqual(errors,[],'browser errors');
  assert.deepEqual(missing,[],'missing assets');
  assert.deepEqual(external,[],'offline mode external requests');
  const cardPage=await browser.newPage();
  await cardPage.route('**/*',r=>r.fulfill({contentType:'text/html',body:'<html><body>Ingress test</body></html>'}));
  await cardPage.goto(`http://127.0.0.1:${port}/card-test`);
  await cardPage.addScriptTag({content:fs.readFileSync('dashboard/tar1090-card.js','utf8')});
  await cardPage.evaluate(()=>{
   window.calls=[];
   const card=document.createElement('tar1090-card');
   card.setConfig({addon:'test_tar1090'});
   card.hass={callWS:async request=>{
    window.calls.push(request);
    if(request.endpoint.endsWith('/info'))return {state:'started',ingress_url:'/api/hassio_ingress/test'};
    if(request.endpoint==='/ingress/session')return {session:'abc123'};
    return {};
   }};
   document.body.appendChild(card);
  });
  await cardPage.waitForFunction(()=>document.querySelector('tar1090-card').ready);
  assert.ok((await cardPage.evaluate(()=>document.cookie)).includes('ingress_session')===false,
    'session cookie should be scoped to ingress path, not dashboard path');
  assert.equal(await cardPage.evaluate(()=>window.calls.filter(c=>c.endpoint==='/ingress/session').length),1);
  const cardSrc=await cardPage.locator('tar1090-card').locator('iframe').getAttribute('src');
  assert.ok(cardSrc.startsWith('/api/hassio_ingress/test/?'));
  await cardPage.evaluate(()=>{const c=document.querySelector('tar1090-card');c.remove();document.body.appendChild(c);});
  assert.equal(await cardPage.evaluate(()=>window.calls.filter(c=>c.endpoint==='/ingress/session').length),1);
  console.log(JSON.stringify({passed:true,inspect,errors,missing,external}));
 } finally {if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
