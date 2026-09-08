"use strict";
// Local app providers; no Exchange proxy, identity, or subscription services.
function createBaseLayers() {
    const providers = [
        ['osm', 'OpenStreetMap', 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', '© OpenStreetMap contributors'],
        ['carto_dark_all', 'CARTO Dark', 'https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png', '© OpenStreetMap contributors © CARTO'],
        ['carto_light_all', 'CARTO Light', 'https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png', '© OpenStreetMap contributors © CARTO'],
        ['esri', 'Satellite', 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', 'Tiles © Esri'],
    ];
    const base = providers.map(([name, title, url, attribution]) => new ol.layer.Tile({
        name, title, type:'base', visible: name === MapType_tar1090,
        source: new ol.source.XYZ({url, attributions: attribution, maxZoom:19})
    }));
    base.push(new ol.layer.Tile({name:'blank', title:'No basemap (offline)', type:'base', visible:MapType_tar1090==='blank'}));
    return new ol.layer.Group({layers:[new ol.layer.Group({name:'world', title:'Basemaps', layers:base})]});
}
