"""Shared CSS / JS / HTML injection for zone map viewers.

Both visualize_binary.py and visualize_zones.py import this.
Zones are rendered entirely from ZONE_DATA in JS — folium only provides
the map container and tile layers. This keeps HTML size ~12 MB instead of 180+ MB.
"""

# (fill, stroke, weight, fillOpacity) — muted distinct palette, consistent tonality
CAT_STYLE = {
     0: ("#7a1a1a", "#550f0f", 2.0, 0.35),   # Large airport       — dark red
     1: ("#7a3d0a", "#552a06", 1.8, 0.32),   # Medium airport      — burnt orange
     2: ("#6b5a08", "#4a3e06", 1.6, 0.30),   # Small airport       — dark amber
     3: ("#0a5252", "#073838", 1.5, 0.30),   # Seaplane base       — dark teal
     4: ("#1a3a7a", "#112860", 1.5, 0.28),   # Heliport            — dark steel blue
     5: ("#4a0f6b", "#330a4a", 1.5, 0.28),   # Balloonport         — dark purple
     6: ("#6b0a14", "#4a0710", 2.2, 0.30),   # FAA Class B         — deep crimson
     7: ("#0a4a2a", "#07331d", 1.8, 0.28),   # FAA Class C         — dark forest green
     8: ("#0a2a52", "#071d3a", 1.5, 0.28),   # FAA Class D         — dark navy
     9: ("#5a0a38", "#3e0727", 2.2, 0.32),   # EU CTR              — dark magenta
    10: ("#1a4a0a", "#123307", 1.8, 0.30),   # EU ATZ              — deep green
    11: ("#3a3a08", "#272706", 1.5, 0.28),   # EU Restricted       — dark olive
    12: ("#083a5a", "#062840", 1.5, 0.28),   # EU TMA              — dark slate blue
    13: ("#0a0814", "#060510", 3.0, 0.50),   # EU Prohibited       — near black / deep indigo
    14: ("#5a3a3a", "#3e2828", 1.5, 0.30),   # Prison              — dark muted rose
    15: ("#5a3a08", "#3e2806", 1.5, 0.28),   # Stadium             — dark sepia
    16: ("#1e3a0a", "#142807", 2.5, 0.38),   # Military base       — dark military green
    17: ("#888888", "#606060", 1.5, 0.12),   # Banned country      — neutral gray (large polygons)
}

_CSS = """\
<style>
*{box-sizing:border-box}
#zt{display:none;position:fixed;z-index:10000;background:rgba(12,12,12,.97);color:#e0e0e0;
  font:12px/1.55 'SF Mono',ui-monospace,Menlo,monospace;padding:10px 14px;border-radius:6px;
  box-shadow:0 6px 28px rgba(0,0,0,.75);max-width:310px;pointer-events:none;border:1px solid #242424}
.zt-z{padding:4px 0}.zt-z:first-child{padding-top:0}.zt-z:last-child{padding-bottom:0}
.zt-f{font-weight:600;color:#f2f2f2;font-size:12px}
.zt-g{color:#787878;font-size:11px;margin-top:3px;letter-spacing:.06em}
.zt-i{color:#424242;font-size:10px;margin-top:2px;font-family:monospace}
.zt-fl{color:#505050;font-size:10px;margin-top:2px}
hr.zt-sep{border:none;border-top:1px solid #222;margin:7px 0}
#rb{display:none;position:fixed;bottom:22px;right:14px;z-index:9999;
  background:rgba(12,12,12,.95);color:#c0c0c0;font:12px/1 system-ui,sans-serif;
  padding:8px 14px;border-radius:6px;border:1px solid #2e2e2e;cursor:pointer;
  gap:8px;align-items:center;box-shadow:0 2px 14px rgba(0,0,0,.6);transition:background .12s}
#rb:hover{background:rgba(24,24,24,.97)}
#zmenu{position:fixed;z-index:10001;background:rgba(12,12,12,.98);color:#d4d4d4;
  font:12px/1.4 system-ui,sans-serif;border-radius:6px;border:1px solid #242424;
  box-shadow:0 6px 28px rgba(0,0,0,.75);overflow:hidden;min-width:200px}
.zmenu-i{padding:9px 14px;cursor:pointer;transition:background .1s;white-space:nowrap}
.zmenu-i:hover{background:rgba(255,255,255,.06)}
.zmenu-s{border-top:1px solid #242424}
.leaflet-control-layers{border-radius:8px!important;border:1px solid #242424!important;
  box-shadow:0 2px 20px rgba(0,0,0,.65)!important;font:12px system-ui,sans-serif!important;
  background:rgba(12,12,12,.96)!important;color:#aaa!important}
.leaflet-control-layers-expanded{padding:10px 14px!important}
.leaflet-control-layers label{cursor:pointer;color:#aaa!important;display:flex!important;align-items:center!important}
.leaflet-control-layers label>div{display:flex!important;align-items:center!important}
.leaflet-control-layers label span{display:inline-flex!important;align-items:center!important}
.leaflet-control-layers-overlays input[type=checkbox]{accent-color:#999;flex-shrink:0;margin-right:9px!important}
.leaflet-control-layers-separator{border-top-color:#242424!important;margin:8px 0!important}
.leaflet-control-layers-toggle{filter:invert(1) brightness(.7)!important}
#bt{display:flex;border:1px solid #2a2a2a;border-radius:5px;overflow:hidden;margin-bottom:6px}
.bt-b{flex:1;padding:5px 10px;background:#141414;color:#555;border:none;cursor:pointer;
  font:11px system-ui,sans-serif;transition:background .15s,color .15s;white-space:nowrap;line-height:1}
.bt-b+.bt-b{border-left:1px solid #2a2a2a}
.bt-b:hover{background:#1e1e1e;color:#aaa}
.bt-a,.bt-a:hover{background:#2a2a2a;color:#e0e0e0}
.lz-sw{display:inline-block;width:11px;height:11px;border-radius:2px;border:1.5px solid;
  margin-right:7px;vertical-align:middle;flex-shrink:0;font-style:normal}
.leaflet-control-layers-overlays label{padding:4px 0!important;line-height:1.6!important}
.leaflet-control-layers-overlays{margin-top:2px}
.lz-grp{color:#484848;font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
  padding:10px 0 4px;margin-top:2px;border-top:1px solid #1e1e1e}
.lz-grp:first-child{padding-top:2px;border-top:none}
.leaflet-control-zoom{border:1px solid #282828!important;border-radius:6px!important;overflow:hidden!important}
.leaflet-control-zoom a{background:rgba(12,12,12,.95)!important;color:#aaa!important;
  border-color:#282828!important;transition:background .12s,color .12s}
.leaflet-control-zoom a:hover{background:rgba(28,28,28,.98)!important;color:#fff!important}
.leaflet-bar{border:none!important}
.leaflet-control-attribution{background:rgba(12,12,12,.7)!important;color:#484848!important;font-size:10px!important}
.leaflet-control-attribution a{color:#545454!important}
#cs{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:9999;
  background:rgba(12,12,12,.96);padding:7px 12px 7px 10px;border-radius:6px;
  box-shadow:0 2px 20px rgba(0,0,0,.6);border:1px solid #242424;
  font:13px/1 system-ui,sans-serif;display:flex;gap:8px;align-items:center;color:#aaa}
#cs-coords{width:215px;padding:5px 11px;border:1px solid #323232;border-radius:4px;
  font:inherit;background:#161616;color:#ddd;outline:none;transition:border-color .15s}
#cs-coords:focus{border-color:#606060;background:#1c1c1c}
#cs-btn{padding:5px 14px;cursor:pointer;border:1px solid #3a3a3a;border-radius:4px;
  background:#252525;color:#ccc;font:inherit;transition:background .15s}
#cs-btn:hover{background:#313131}
#cs-err{position:absolute;top:calc(100% + 6px);left:50%;transform:translateX(-50%);
  background:#180000;color:#ff5a5a;font-size:11px;padding:4px 10px;border-radius:4px;
  border:1px solid #3e0000;white-space:nowrap;display:none}
</style>"""

_STATIC_HTML = """\
<div id="zt"></div>
<div id="rb" onclick="window._restoreAllZones()">
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="#888"
       stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M2 8a6 6 0 1 1 1.5 4.2"/><polyline points="1,5 2,8 5,7"/>
  </svg>
  <span id="rb-n"></span>
</div>"""

# JS template — __MAP__ replaced at runtime with the folium map variable name
_JS_TEMPLATE = """\
<script>
(function(){
var _l={},_h={},_fgs={},_cm=null,_tt=null;

function _pip(lat,lon,z){
  if(z.t==='c'){
    var dy=(lat-z.clat)*111320,dx=(lon-z.clon)*111320*Math.cos(z.clat*Math.PI/180);
    return dy*dy+dx*dx<=z.r*z.r;
  }
  var p=z.pts,n=p.length,ins=false;
  for(var i=0,j=n-1;i<n;j=i++){
    var yi=p[i][0],xi=p[i][1],yj=p[j][0],xj=p[j][1];
    if((yi>lat)!=(yj>lat)&&lon<(xj-xi)*(lat-yi)/(yj-yi)+xi)ins=!ins;
  }
  return ins;
}

function _at(lat,lon,all){
  var res=[];
  for(var i=0;i<ZONE_DATA.length;i++){
    if(!all&&_h[i])continue;
    var z=ZONE_DATA[i],b=z.b;
    if(lat<b[0]||lat>b[1]||lon<b[2]||lon>b[3])continue;
    if(_pip(lat,lon,z))res.push(i);
  }
  return res;
}

function _showTt(hits,cx,cy){
  _tt=_tt||document.getElementById('zt');
  if(!hits.length){_tt.style.display='none';return;}
  // Deduplicate by zone ID (same ID = same zone in multiple tiles)
  var seen={},deduped=[];
  for(var k=0;k<hits.length;k++){var zid=ZONE_DATA[hits[k]].zid;if(!seen[zid]){seen[zid]=1;deduped.push(hits[k]);}}
  var h='';
  for(var k=0;k<deduped.length;k++){
    var z=ZONE_DATA[deduped[k]];
    if(k)h+='<hr class="zt-sep">';
    h+='<div class="zt-z"><div class="zt-f">'+z.f+'</div>'+
       '<div class="zt-g">'+z.tag+'</div>'+
       '<div class="zt-i">'+z.zid+'</div>'+
       (z.fl?'<div class="zt-fl">Min floor: '+z.fl+' m</div>':'')+
       '</div>';
  }
  _tt.innerHTML=h;_tt.style.display='block';
  var x=cx+18,y=cy-10,w=_tt.offsetWidth,hh=_tt.offsetHeight,
      vw=window.innerWidth,vh=window.innerHeight;
  if(x+w>vw-10)x=cx-w-10;
  if(y+hh>vh-10)y=vh-hh-10;
  if(y<10)y=10;
  _tt.style.left=x+'px';_tt.style.top=y+'px';
}

function _setVis(zi,show){
  var l=_l[zi];if(!l)return;
  if(show){
    var st=CAT_STYLES[ZONE_DATA[zi].cat];
    l.setStyle({color:st[1],fillColor:st[0],weight:st[2],opacity:.85,fillOpacity:st[3]});
  }else{
    l.setStyle({opacity:0,fillOpacity:0});
  }
}
function _hideZone(zi){_setVis(zi,false);_h[zi]=1;_upBtn();}
function _showZone(zi){_setVis(zi,true);delete _h[zi];_upBtn();}
function _showAll(){Object.keys(_h).forEach(function(z){_showZone(+z);});}
window._restoreAllZones=_showAll;

function _upBtn(){
  var btn=document.getElementById('rb'),n=Object.keys(_h).length;
  btn.style.display=n?'flex':'none';
  document.getElementById('rb-n').textContent=n+(n===1?' hidden zone':' hidden zones');
}

function _clMenu(){
  if(_cm){_cm.remove();_cm=null;}
  document.removeEventListener('click',_clMenu);
}

function _rclick(lat,lon,cx,cy){
  _clMenu();
  var vis=_at(lat,lon,false);
  var hid=_at(lat,lon,true).filter(function(i){return!!_h[i];});
  if(!vis.length&&!hid.length)return;
  var items=[];
  vis.forEach(function(i){var z=ZONE_DATA[i];items.push({l:'Hide — '+z.f+' ('+z.tag+')',fn:function(){_hideZone(i);}});});
  hid.forEach(function(i){var z=ZONE_DATA[i];items.push({l:'Show — '+z.f+' ('+z.tag+')',fn:function(){_showZone(i);}});});
  if(items.length===1){items[0].fn();return;}
  _cm=document.createElement('div');_cm.id='zmenu';
  var sep=false;
  items.forEach(function(it,k){
    if(!sep&&k>0&&it.l[0]==='S'&&items[k-1].l[0]==='H'){sep=true;}
    var d=document.createElement('div');
    d.className='zmenu-i'+(sep&&it.l[0]==='S'&&(k===0||items[k-1].l[0]==='H')?' zmenu-s':'');
    d.textContent=it.l;
    d.onclick=function(e){e.stopPropagation();it.fn();_clMenu();};
    _cm.appendChild(d);
  });
  var mh=_cm.childElementCount*38+8;
  _cm.style.left=Math.min(cx,window.innerWidth-220)+'px';
  _cm.style.top=Math.min(cy,window.innerHeight-mh)+'px';
  document.body.appendChild(_cm);
  setTimeout(function(){document.addEventListener('click',_clMenu,{once:true});},0);
}

function _styleCtrl(mp,base){
  setTimeout(function(){
    // Replace radio buttons with pill toggle
    var bs=document.querySelector('.leaflet-control-layers-base');
    if(bs){
      var pill=document.createElement('div');pill.id='bt';
      var bk=Object.keys(base);
      bk.forEach(function(name,i){
        var btn=document.createElement('button');
        btn.className='bt-b'+(mp.hasLayer(base[name])?' bt-a':'');
        btn.textContent=name;
        btn.onclick=function(){
          bk.forEach(function(n){
            if(n===name){if(!mp.hasLayer(base[n]))base[n].addTo(mp);}
            else{if(mp.hasLayer(base[n]))mp.removeLayer(base[n]);}
          });
          document.querySelectorAll('.bt-b').forEach(function(b){b.classList.toggle('bt-a',b===btn);});
        };
        pill.appendChild(btn);
      });
      bs.replaceWith(pill);
    }
    // Group headers + color swatches on overlay labels
    var olbls=document.querySelectorAll('.leaflet-control-layers-overlays label');
    var lastGrp=null;
    olbls.forEach(function(lbl,i){
      var c=ZONE_CATS[i];if(!c)return;
      if(c.group&&c.group!==lastGrp){
        var hdr=document.createElement('div');
        hdr.className='lz-grp';hdr.textContent=c.group;
        lbl.parentNode.insertBefore(hdr,lbl);
        lastGrp=c.group;
      }
      var st=CAT_STYLES[c.cat];if(!st)return;
      var sp=lbl.querySelector('span');if(!sp)return;
      var sw=document.createElement('i');
      sw.className='lz-sw';sw.style.background=st[0];sw.style.borderColor=st[1];
      sp.insertBefore(sw,sp.firstChild);
    });
  },150);
}

function _init(){
  var mp=window['__MAP__'];
  if(!mp){setTimeout(_init,100);return;}

  // Restrict to one world copy
  mp.setMaxBounds([[-90,-180],[90,180]]);
  mp.options.maxBoundsViscosity=1.0;
  mp.setMinZoom(2);

  // Find tile layers for base map control
  var base={};
  mp.eachLayer(function(l){
    if(!l._url)return;
    if(l._url.indexOf('Street_Map')>-1)base['Streets']=l;
    else if(l._url.indexOf('Imagery')>-1)base['Satellite']=l;
  });
  // Only keep the first base layer visible; pill toggle handles the rest
  var _bk=Object.keys(base);
  _bk.forEach(function(name,i){if(i>0&&mp.hasLayer(base[name]))mp.removeLayer(base[name]);});

  // Create one layerGroup per category
  var overlays={};
  ZONE_CATS.forEach(function(c){
    var lg=L.layerGroup().addTo(mp);
    _fgs[c.cat]=lg;
    overlays[c.label]=lg;
  });

  // Render all zones from ZONE_DATA
  var cv=L.canvas();
  ZONE_DATA.forEach(function(z,zi){
    var st=CAT_STYLES[z.cat];
    var opts={color:st[1],fillColor:st[0],weight:st[2],opacity:.85,fillOpacity:st[3],renderer:cv};
    var layer;
    if(z.t==='c'){
      layer=L.circle([z.clat,z.clon],Object.assign({radius:z.r},opts));
    }else{
      layer=L.polygon(z.pts,opts);
    }
    _l[zi]=layer;
    if(_fgs[z.cat])_fgs[z.cat].addLayer(layer);
  });

  // Unified layer control (tiles + zone categories)
  L.control.layers(base,overlays,{collapsed:false}).addTo(mp);
  _styleCtrl(mp,base);

  // Events
  _tt=document.getElementById('zt');
  mp.on('mousemove',function(e){
    var oe=e.originalEvent;
    _showTt(_at(e.latlng.lat,e.latlng.lng,false),oe.clientX,oe.clientY);
  });
  mp.on('mouseout',function(){if(_tt)_tt.style.display='none';});
  mp.on('contextmenu',function(e){
    var oe=e.originalEvent;
    L.DomEvent.preventDefault(oe);
    if(_tt)_tt.style.display='none';
    _rclick(e.latlng.lat,e.latlng.lng,oe.clientX,oe.clientY);
  });
  document.addEventListener('keydown',function(e){
    if((e.ctrlKey||e.metaKey)&&e.key==='z'){e.preventDefault();_showAll();}
  });
}

document.addEventListener('DOMContentLoaded',function(){setTimeout(_init,200);});
})();
</script>"""


def folium_style(cat):
    """Return Leaflet polygon style kwargs for a category number (for any folium shapes still needed)."""
    fill, stroke, weight, opacity = CAT_STYLE.get(cat, ("#555", "#333", 1.5, 0.22))
    return {"color": stroke, "fillColor": fill, "weight": weight,
            "fillOpacity": opacity, "opacity": 0.85}


def cat_styles_json():
    pairs = ",".join(
        f'{k}:["{v[0]}","{v[1]}",{v[2]},{v[3]}]'
        for k, v in CAT_STYLE.items()
    )
    return "{" + pairs + "}"


def make_extras(map_var, zone_data_json, zone_cats_json):
    """Return full HTML/CSS/JS block to inject into a folium map."""
    data_script = (
        f'<script>'
        f'var ZONE_DATA={zone_data_json};'
        f'var ZONE_CATS={zone_cats_json};'
        f'var CAT_STYLES={cat_styles_json()};'
        f'</script>'
    )
    js = _JS_TEMPLATE.replace('__MAP__', map_var)
    search = _search_bar_js(map_var)
    return _CSS + _STATIC_HTML + data_script + js + search


def _search_bar_js(map_var):
    return f"""\
<div id="cs">
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#555"
       stroke-width="2" stroke-linecap="round"><circle cx="6.5" cy="6.5" r="4.5"/>
    <line x1="10" y1="10" x2="14" y2="14"/></svg>
  <input id="cs-coords" type="text" placeholder="lat, lon">
  <button id="cs-btn" onclick="csGo()">Go</button>
  <span id="cs-err">&#9888; format: lat, lon</span>
</div>
<script>
var _csPin=null;
function csGo(){{
  var raw=document.getElementById('cs-coords').value.trim();
  var err=document.getElementById('cs-err');
  var parts=raw.split(',');
  var lat=parseFloat((parts[0]||'').trim()),lon=parseFloat((parts[1]||'').trim());
  if(parts.length<2||isNaN(lat)||isNaN(lon)){{
    err.style.display='block';setTimeout(function(){{err.style.display='none';}},2500);return;
  }}
  err.style.display='none';
  var mp=window['{map_var}'];if(!mp)return;
  mp.setView([lat,lon],13);
  if(_csPin)mp.removeLayer(_csPin);
  _csPin=L.marker([lat,lon]).addTo(mp)
    .bindPopup('&#128205; '+lat.toFixed(5)+', '+lon.toFixed(5)).openPopup();
}}
document.getElementById('cs-coords').addEventListener('keydown',function(e){{if(e.key==='Enter')csGo();}});
</script>"""
