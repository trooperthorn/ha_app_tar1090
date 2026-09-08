/* HA ingress session flow follows frontend/src/data/hassio/ingress.ts. */
class Tar1090Card extends HTMLElement {
    constructor() { super(); this.attachShadow({mode:'open'}); }
    setConfig(config) {
        clearTimeout(this.timer);
        if (!config.addon || !/^[a-zA-Z0-9_-]+$/.test(config.addon)) throw new Error('Set addon to the full installed app slug');
        this.config = config;
        this.ready = false;
        this.shadowRoot.innerHTML = '<ha-card><div class="message">Connecting to aircraft app…</div><iframe title="Local aircraft"></iframe></ha-card>';
        const style = document.createElement('style');
        style.textContent = 'iframe{width:100%;height:'+ Math.max(200,Math.min(2000,Number(config.height)||600))+'px;border:0;display:none} .message{padding:16px}';
        this.shadowRoot.append(style);
        this.open();
    }
    set hass(hass) { this._hass = hass; this.open(); }
    connectedCallback() { if (this.ready) this.renew(); else this.open(); }
    disconnectedCallback() { clearTimeout(this.timer); }
    async api(endpoint, method='get', data) {
        return this._hass.callWS({type:'supervisor/api',endpoint,method,...(data?{data}:{})});
    }
    async open() {
        if (!this._hass || !this.config || this.busy || this.ready || !this.isConnected) return;
        this.busy = true;
        try {
            const info = await this.api('/addons/'+this.config.addon+'/info');
            if (info.state !== 'started' || !info.ingress_url?.startsWith('/api/hassio_ingress/')) throw new Error('App must be started with ingress enabled');
            await this.session();
            const frame = this.shadowRoot.querySelector('iframe');
            const query = new URLSearchParams(this.config.query || 'zoom=9&hideButtons&hideSideBar&centerReceiver&mapDim=0.4&iconScale=0.7&labelScale=0.75&extendedLabels=2&rangeRings=0&filterAltMax=10000&mapOrientation=150&enableLabels');
            frame.src = info.ingress_url.replace(/\/?$/, '/')+'?'+query.toString();
            frame.style.display='block';
            this.shadowRoot.querySelector('.message').hidden=true;
            this.ready=true;
            this.renew();
        } catch(error) {
            this.shadowRoot.querySelector('.message').textContent='Aircraft app: '+error.message+' (HA permission to access this app is required.)';
            this.timer=setTimeout(()=>this.open(),30000);
        } finally { this.busy=false; }
    }
    async session() {
        const {session} = await this.api('/ingress/session','post');
        if (!/^[a-zA-Z0-9_-]+$/.test(session)) throw new Error('Invalid ingress session');
        document.cookie='ingress_session='+session+';path=/api/hassio_ingress/;SameSite=Strict'+(location.protocol==='https:'?';Secure':'');
        this.ingressSession=session;
    }
    renew() {
        clearTimeout(this.timer);
        this.timer=setTimeout(async()=>{
            if (!this.isConnected) return;
            try { await this.api('/ingress/validate_session','post',{session:this.ingressSession}); }
            catch (_) { try { await this.session(); } catch (_) { this.ready=false; this.open(); return; } }
            this.renew();
        },60000);
    }
    getCardSize() { return 8; }
}
customElements.define('tar1090-card',Tar1090Card);
window.customCards=window.customCards||[];
window.customCards.push({type:'tar1090-card',name:'Local Aircraft',description:'Authenticated HA App ingress map'});
