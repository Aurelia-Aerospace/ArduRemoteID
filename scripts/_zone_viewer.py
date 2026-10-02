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
#db{position:fixed;bottom:22px;left:14px;z-index:9999;
  background:rgba(12,12,12,.95);color:#c0c0c0;font:12px/1 system-ui,sans-serif;
  padding:8px 14px;border-radius:6px;border:1px solid #2e2e2e;cursor:pointer;
  display:flex;gap:7px;align-items:center;box-shadow:0 2px 14px rgba(0,0,0,.6);
  transition:background .12s,color .12s,border-color .12s}
#db:hover{background:rgba(24,24,24,.97);color:#e0e0e0}
#db.db-a{border-color:#4a4a22;color:#c8c060;background:rgba(18,16,4,.97)}
#dh{display:none;position:fixed;bottom:62px;left:14px;z-index:9998;
  background:rgba(12,12,12,.92);color:#787878;font:11px/1.5 system-ui,sans-serif;
  padding:7px 12px;border-radius:5px;border:1px solid #282818;
  box-shadow:0 2px 12px rgba(0,0,0,.5);gap:10px;align-items:center}
#dh-fin{padding:3px 10px;background:#1a1a08;border:1px solid #3a3a1a;border-radius:3px;
  color:#b8b840;cursor:pointer;font:11px system-ui,sans-serif;transition:background .12s;flex-shrink:0}
#dh-fin:hover{background:#252510}
#dr{display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
  z-index:10002;background:rgba(10,10,10,.98);color:#d4d4d4;
  font:12px/1.5 system-ui,sans-serif;border-radius:8px;border:1px solid #282828;
  box-shadow:0 8px 40px rgba(0,0,0,.85);width:340px;max-height:70vh;
  flex-direction:column;overflow:hidden}
#dr-hd{display:flex;align-items:center;justify-content:space-between;
  padding:12px 16px;border-bottom:1px solid #1e1e1e;flex-shrink:0}
#dr-hd h3{margin:0;font-size:13px;font-weight:600;color:#f0f0f0}
#dr-cl{background:none;border:none;color:#666;cursor:pointer;font-size:16px;
  line-height:1;padding:2px 4px;border-radius:3px;transition:color .12s}
#dr-cl:hover{color:#aaa}
#dr-list{overflow-y:auto;padding:10px 16px;flex:1;min-height:0}
#dr-list::-webkit-scrollbar{width:4px}
#dr-list::-webkit-scrollbar-track{background:transparent}
#dr-list::-webkit-scrollbar-thumb{background:#2a2a2a;border-radius:2px}
.dr-empty{color:#484848;text-align:center;padding:20px 0;font-size:12px}
.dr-group{margin-bottom:8px}
.dr-ghead{color:#484848;font-size:10px;font-weight:700;text-transform:uppercase;
  letter-spacing:.1em;padding:8px 0 4px;border-top:1px solid #1a1a1a;margin-bottom:2px}
.dr-group:first-child .dr-ghead{border-top:none;padding-top:2px}
.dr-item{display:flex;gap:10px;align-items:center;padding:2px 0}
.dr-tag{color:#686868;font-size:11px;font-family:monospace;min-width:72px}
.dr-zid{font-family:monospace;font-size:11px;color:#c8c8c8}
#dr-ft{display:flex;gap:8px;padding:10px 16px;border-top:1px solid #1e1e1e;
  flex-shrink:0;align-items:center}
#dr-cp{flex:1;padding:7px 12px;background:#1e1e1e;border:1px solid #383838;border-radius:5px;
  color:#b8b8b8;font:12px system-ui,sans-serif;cursor:pointer;
  transition:background .15s,color .15s}
#dr-cp:hover{background:#282828;color:#d8d8d8}
#dr-cnt{color:#484848;font-size:11px;white-space:nowrap}
</style>"""

_STATIC_HTML = """\
<div id="zt"></div>
<div id="rb" onclick="window._restoreAllZones()">
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="#888"
       stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M2 8a6 6 0 1 1 1.5 4.2"/><polyline points="1,5 2,8 5,7"/>
  </svg>
  <span id="rb-n"></span>
</div>
<button id="db" onclick="window._toggleDraw()">
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor"
       stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <polygon points="8,2 14,7 11,14 5,14 2,7"/>
  </svg>
  Draw Zone
</button>
<div id="dh">
  <span>Click to add vertices &nbsp;&middot;&nbsp; Right-click or Finish to close &nbsp;&middot;&nbsp; Esc to cancel</span>
  <button id="dh-fin" onclick="window._finishDraw()">Finish</button>
</div>
<div id="dr">
  <div id="dr-hd">
    <h3>Zones in drawn area</h3>
    <button id="dr-cl" onclick="document.getElementById('dr').style.display='none'">&#x2715;</button>
  </div>
  <div id="dr-list"></div>
  <div id="dr-ft">
    <button id="dr-cp" onclick="window._copyIds()">Copy for SET_SECURE_CONFIG</button>
    <span id="dr-cnt"></span>
  </div>
</div>"""

# JS template — __MAP__ replaced at runtime with the folium map variable name
_JS_TEMPLATE = """\
<script>
(function(){
var _l={},_h={},_fgs={},_cm=null,_tt=null;
var _mp=null,_dv=[],_dPoly=null,_dDots=[],_dPrev=null,_dMode=false,_drz=[];

// ── Zone hit-test ─────────────────────────────────────────────────────────────
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

// ── Draw-polygon intersection geometry ───────────────────────────────────────
function _segsX(ax,ay,bx,by,cx,cy,dx,dy){
  var d1x=bx-ax,d1y=by-ay,d2x=dx-cx,d2y=dy-cy;
  var cross=d1x*d2y-d1y*d2x;
  if(Math.abs(cross)<1e-10)return false;
  var tx=cx-ax,ty=cy-ay;
  var t=(tx*d2y-ty*d2x)/cross,u=(tx*d1y-ty*d1x)/cross;
  return t>=0&&t<=1&&u>=0&&u<=1;
}
function _pipArr(lat,lon,ring){
  var n=ring.length,ins=false,j=n-1;
  for(var i=0;i<n;j=i++){
    var yi=ring[i][0],xi=ring[i][1],yj=ring[j][0],xj=ring[j][1];
    if((yi>lat)!=(yj>lat)&&lon<(xj-xi)*(lat-yi)/(yj-yi)+xi)ins=!ins;
  }
  return ins;
}
function _ptSegDsq(px,py,ax,ay,bx,by){
  var dx=bx-ax,dy=by-ay,len2=dx*dx+dy*dy;
  if(len2<1e-12)return (px-ax)*(px-ax)+(py-ay)*(py-ay);
  var t=Math.max(0,Math.min(1,((px-ax)*dx+(py-ay)*dy)/len2));
  var rx=ax+t*dx-px,ry=ay+t*dy-py;
  return rx*rx+ry*ry;
}
function _circleHits(clat,clon,r,ring){
  if(_pipArr(clat,clon,ring))return true;
  var cos=Math.cos(clat*Math.PI/180),n=ring.length,r2=r*r;
  for(var i=0;i<n;i++){
    var dy=(ring[i][0]-clat)*111320,dx=(ring[i][1]-clon)*111320*cos;
    if(dy*dy+dx*dx<=r2)return true;
  }
  for(var i=0,j=n-1;i<n;j=i++){
    var ay=(ring[j][0]-clat)*111320,ax=(ring[j][1]-clon)*111320*cos;
    var by=(ring[i][0]-clat)*111320,bx=(ring[i][1]-clon)*111320*cos;
    if(_ptSegDsq(0,0,ax,ay,bx,by)<=r2)return true;
  }
  return false;
}
function _polyHits(pts,ring){
  var n1=pts.length,n2=ring.length;
  for(var i=0;i<n1;i++)if(_pipArr(pts[i][0],pts[i][1],ring))return true;
  for(var i=0;i<n2;i++)if(_pipArr(ring[i][0],ring[i][1],pts))return true;
  for(var i=0,j=n1-1;i<n1;j=i++)
    for(var k=0,l=n2-1;k<n2;l=k++)
      if(_segsX(pts[j][0],pts[j][1],pts[i][0],pts[i][1],
                ring[l][0],ring[l][1],ring[k][0],ring[k][1]))return true;
  return false;
}
function _findInDraw(ring){
  var rl0=Infinity,rl1=-Infinity,rn0=Infinity,rn1=-Infinity;
  for(var i=0;i<ring.length;i++){
    if(ring[i][0]<rl0)rl0=ring[i][0];if(ring[i][0]>rl1)rl1=ring[i][0];
    if(ring[i][1]<rn0)rn0=ring[i][1];if(ring[i][1]>rn1)rn1=ring[i][1];
  }
  var seen={},res=[];
  for(var i=0;i<ZONE_DATA.length;i++){
    var z=ZONE_DATA[i],b=z.b;
    if(b[1]<rl0||b[0]>rl1||b[3]<rn0||b[2]>rn1)continue;
    if(seen[z.zid])continue;
    var hit=(z.t==='c')?_circleHits(z.clat,z.clon,z.r,ring):_polyHits(z.pts,ring);
    if(hit){seen[z.zid]=1;res.push(z);}
  }
  res.sort(function(a,b){return a.cat-b.cat||(a.zid<b.zid?-1:a.zid>b.zid?1:0);});
  return res;
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
function _showTt(hits,cx,cy){
  _tt=_tt||document.getElementById('zt');
  if(!hits.length){_tt.style.display='none';return;}
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

// ── Hide / show zones ─────────────────────────────────────────────────────────
function _setVis(zi,show){
  var l=_l[zi];if(!l)return;
  if(show){var st=CAT_STYLES[ZONE_DATA[zi].cat];
    l.setStyle({color:st[1],fillColor:st[0],weight:st[2],opacity:.85,fillOpacity:st[3]});}
  else{l.setStyle({opacity:0,fillOpacity:0});}
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

// ── Context menu ──────────────────────────────────────────────────────────────
function _clMenu(){if(_cm){_cm.remove();_cm=null;}document.removeEventListener('click',_clMenu);}

function _rclick(lat,lon,cx,cy){
  _clMenu();
  var vis=_at(lat,lon,false),hid=_at(lat,lon,true).filter(function(i){return!!_h[i];});
  if(!vis.length&&!hid.length)return;
  var items=[];
  vis.forEach(function(i){var z=ZONE_DATA[i];items.push({l:'Hide — '+z.f+' ('+z.tag+')',fn:function(){_hideZone(i);}});});
  hid.forEach(function(i){var z=ZONE_DATA[i];items.push({l:'Show — '+z.f+' ('+z.tag+')',fn:function(){_showZone(i);}});});
  if(items.length===1){items[0].fn();return;}
  _cm=document.createElement('div');_cm.id='zmenu';
  var sep=false;
  items.forEach(function(it,k){
    if(!sep&&k>0&&it.l[0]==='S'&&items[k-1].l[0]==='H')sep=true;
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

// ── Layer control styling ─────────────────────────────────────────────────────
function _styleCtrl(mp,base){
  setTimeout(function(){
    var bs=document.querySelector('.leaflet-control-layers-base');
    if(bs){
      var pill=document.createElement('div');pill.id='bt';
      var bk=Object.keys(base);
      bk.forEach(function(name){
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
    var olbls=document.querySelectorAll('.leaflet-control-layers-overlays label');
    var lastGrp=null;
    olbls.forEach(function(lbl,i){
      var c=ZONE_CATS[i];if(!c)return;
      if(c.group&&c.group!==lastGrp){
        var hdr=document.createElement('div');hdr.className='lz-grp';hdr.textContent=c.group;
        lbl.parentNode.insertBefore(hdr,lbl);lastGrp=c.group;
      }
      var st=CAT_STYLES[c.cat];if(!st)return;
      var sp=lbl.querySelector('span');if(!sp)return;
      var sw=document.createElement('i');sw.className='lz-sw';
      sw.style.background=st[0];sw.style.borderColor=st[1];
      sp.insertBefore(sw,sp.firstChild);
    });
  },150);
}

// ── Draw polygon tool ─────────────────────────────────────────────────────────
function _clearDraw(){
  _dDots.forEach(function(d){if(_mp&&_mp.hasLayer(d))_mp.removeLayer(d);});
  _dDots=[];
  if(_dPoly&&_mp&&_mp.hasLayer(_dPoly)){_mp.removeLayer(_dPoly);_dPoly=null;}
  if(_dPrev&&_mp&&_mp.hasLayer(_dPrev)){_mp.removeLayer(_dPrev);_dPrev=null;}
}
window._clearDrawPoly=_clearDraw;

function _dbLabel(active){
  var btn=document.getElementById('db');if(!btn)return;
  if(active){btn.textContent='✕ Cancel';btn.classList.add('db-a');}
  else{
    btn.innerHTML='<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor"'
      +' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
      +'<polygon points="8,2 14,7 11,14 5,14 2,7"/></svg> Draw Zone';
    btn.classList.remove('db-a');
  }
}

function _startDraw(){
  _dMode=true;_dv=[];
  _clearDraw();
  _dbLabel(true);
  var dh=document.getElementById('dh');if(dh)dh.style.display='flex';
  if(_mp)_mp.getContainer().style.cursor='crosshair';
}
function _cancelDraw(){
  _dMode=false;_dv=[];
  _clearDraw();
  _dbLabel(false);
  var dh=document.getElementById('dh');if(dh)dh.style.display='none';
  if(_mp)_mp.getContainer().style.cursor='';
}
function _toggleDraw(){if(_dMode)_cancelDraw();else _startDraw();}
window._toggleDraw=_toggleDraw;

function _addVert(lat,lon){
  _dv.push([lat,lon]);
  var dot=L.circleMarker([lat,lon],{radius:4,color:'#c8c060',fillColor:'#c8c060',
    fillOpacity:1,weight:1.5,interactive:false}).addTo(_mp);
  _dDots.push(dot);
  if(_dv.length>=2){
    var ring=_dv.length>=3?_dv.concat([_dv[0]]):_dv;
    if(_dPoly){_dPoly.setLatLngs(ring);}
    else{_dPoly=L.polyline(ring,{color:'#c8c060',weight:1.5,dashArray:'6,4',
      opacity:.85,interactive:false}).addTo(_mp);}
  }
}

function _updatePrev(lat,lon){
  if(!_dv.length)return;
  var last=_dv[_dv.length-1],pts=[last,[lat,lon]];
  if(_dPrev){_dPrev.setLatLngs(pts);}
  else{_dPrev=L.polyline(pts,{color:'#c8c060',weight:1.2,dashArray:'3,5',
    opacity:.5,interactive:false}).addTo(_mp);}
}

function _finishDraw(){
  if(_dv.length<3){_cancelDraw();return;}
  if(_dPrev&&_mp.hasLayer(_dPrev)){_mp.removeLayer(_dPrev);_dPrev=null;}
  if(_dPoly)_dPoly.setStyle({dashArray:null,opacity:1,weight:2});
  var ring=_dv.slice();
  _dMode=false;
  _dbLabel(false);
  var dh=document.getElementById('dh');if(dh)dh.style.display='none';
  if(_mp)_mp.getContainer().style.cursor='';
  _drz=_findInDraw(ring);
  _showDrawResult(_drz);
}
window._finishDraw=_finishDraw;

function _showDrawResult(zones){
  var dlg=document.getElementById('dr');if(!dlg)return;
  var list=document.getElementById('dr-list');if(!list)return;
  var cnt=document.getElementById('dr-cnt');
  if(cnt)cnt.textContent=zones.length+(zones.length===1?' zone':' zones');
  if(!zones.length){
    list.innerHTML='<div class="dr-empty">No restricted zones found in drawn area.</div>';
  }else{
    var h='',lastCat=-1;
    zones.forEach(function(z){
      if(z.cat!==lastCat){
        if(lastCat>=0)h+='</div>';
        h+='<div class="dr-group"><div class="dr-ghead">'+z.f+'</div>';
        lastCat=z.cat;
      }
      h+='<div class="dr-item"><span class="dr-tag">'+z.tag+'</span>'
        +'<span class="dr-zid">'+z.zid+'</span></div>';
    });
    if(lastCat>=0)h+='</div>';
    list.innerHTML=h;
  }
  dlg.style.display='flex';
}

function _copyIds(){
  if(!_drz.length)return;
  var ids=_drz.map(function(z){return z.zid;}).join(' ');
  var txt='SET_SECURE_CONFIG ZONE_UNLOCK '+ids;
  var btn=document.getElementById('dr-cp');
  function ack(){
    if(!btn)return;
    var orig=btn.textContent;
    btn.textContent='✓ Copied!';
    setTimeout(function(){btn.textContent=orig;},1500);
  }
  if(navigator.clipboard){navigator.clipboard.writeText(txt).then(ack);}
  else{
    var ta=document.createElement('textarea');ta.value=txt;
    ta.style.cssText='position:fixed;opacity:0;pointer-events:none';
    document.body.appendChild(ta);ta.select();document.execCommand('copy');
    document.body.removeChild(ta);ack();
  }
}
window._copyIds=_copyIds;

// ── Map init ──────────────────────────────────────────────────────────────────
function _init(){
  var mp=window['__MAP__'];
  if(!mp){setTimeout(_init,100);return;}
  _mp=mp;

  mp.setMaxBounds([[-90,-180],[90,180]]);
  mp.options.maxBoundsViscosity=1.0;
  mp.setMinZoom(2);

  var base={};
  mp.eachLayer(function(l){
    if(!l._url)return;
    if(l._url.indexOf('Street_Map')>-1)base['Streets']=l;
    else if(l._url.indexOf('Imagery')>-1)base['Satellite']=l;
  });
  var _bk=Object.keys(base);
  _bk.forEach(function(name,i){if(i>0&&mp.hasLayer(base[name]))mp.removeLayer(base[name]);});

  var overlays={};
  ZONE_CATS.forEach(function(c){
    var lg=L.layerGroup().addTo(mp);_fgs[c.cat]=lg;overlays[c.label]=lg;
  });

  var cv=L.canvas();
  ZONE_DATA.forEach(function(z,zi){
    var st=CAT_STYLES[z.cat];
    var opts={color:st[1],fillColor:st[0],weight:st[2],opacity:.85,fillOpacity:st[3],renderer:cv};
    var layer=(z.t==='c')
      ?L.circle([z.clat,z.clon],Object.assign({radius:z.r},opts))
      :L.polygon(z.pts,opts);
    _l[zi]=layer;
    if(_fgs[z.cat])_fgs[z.cat].addLayer(layer);
  });

  L.control.layers(base,overlays,{collapsed:false}).addTo(mp);
  _styleCtrl(mp,base);

  _tt=document.getElementById('zt');

  mp.on('click',function(e){
    if(!_dMode)return;
    _addVert(e.latlng.lat,e.latlng.lng);
  });
  mp.on('mousemove',function(e){
    if(_dMode){
      if(_tt)_tt.style.display='none';
      _updatePrev(e.latlng.lat,e.latlng.lng);
      return;
    }
    var oe=e.originalEvent;
    _showTt(_at(e.latlng.lat,e.latlng.lng,false),oe.clientX,oe.clientY);
  });
  mp.on('mouseout',function(){if(_tt)_tt.style.display='none';});
  mp.on('contextmenu',function(e){
    var oe=e.originalEvent;
    L.DomEvent.preventDefault(oe);
    if(_dMode){if(_dv.length>=3)_finishDraw();return;}
    if(_tt)_tt.style.display='none';
    _rclick(e.latlng.lat,e.latlng.lng,oe.clientX,oe.clientY);
  });
  document.addEventListener('keydown',function(e){
    if((e.ctrlKey||e.metaKey)&&e.key==='z'){e.preventDefault();_showAll();}
    if(e.key==='Escape'&&_dMode)_cancelDraw();
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
