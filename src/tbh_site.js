// Farm watch controls are served by the local run.bat HTTP server.
function farmEscape(value){
  return String(value==null?'':value).replace(/[&<>"']/g,function(ch){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];});
}
function farmAccountForButton(btn){
  var account=btn.getAttribute('data-conta')||'';
  try{if(!account&&typeof cur==='number'&&cur>=0&&B.urls&&B.urls[cur]){var match=(B.urls[cur]||'').match(/\\|user=([^|]+)/);if(match)account=match[1];}}catch(e){}
  return account;
}
function farmApi(action,name,account){
  if(!FARM_API_URL||!window.__TBH_FARM_API_TOKEN__||window.__TBH_FARM_API_TOKEN__==='__TBH_FARM_API_TOKEN__')return Promise.reject(new Error('Abre a dashboard no endereco local iniciado pelo run.bat.'));
  var options={method:action?'POST':'GET',headers:{'X-TBH-Farm-Token':window.__TBH_FARM_API_TOKEN__},cache:'no-store'};
  if(action){options.headers['Content-Type']='application/json';options.body=JSON.stringify({action:action,name:name,conta:account||''});}
  return fetch(FARM_API_URL,options).then(function(response){return response.json().then(function(data){if(!response.ok||!data.ok)throw new Error(data.erro||'Nao foi possivel atualizar os alertas.');return data;});});
}
function syncFarmButtons(w){
  document.querySelectorAll('.ffarmbtn').forEach(function(button){
    var name=(button.getAttribute('data-farm')||'').trim().toLowerCase(),account=farmAccountForButton(button).trim().toLowerCase();
    var target=(w.targets||[]).find(function(target){var targetName=String(target.name||'').trim().toLowerCase(),targetAccount=String(target.conta||'').trim().toLowerCase();return name===targetName&&(!targetAccount||!account||targetAccount===account||account.endsWith('('+targetAccount+')'));});
    var active=!!target,paused=active&&!!target.paused;
    button.classList.toggle('on',active);button.disabled=active;button.textContent=paused?'⏸ Pausado':active?'🔔 A vigiar':'🎯 Vigiar item';
    button.title=paused?'Este item esta em pausa. Usa Retomar ou Parar na lista de alertas.':active?'Este item esta na lista. Usa Parar na lista de alertas para o remover.':'Adicionar este item a lista de alertas.';
  });
}
function farmAction(action,name,account){
  var bar=document.getElementById('farmWatchBar');
  if(bar){bar.classList.add('show');bar.textContent=action==='remove'?'A remover o alerta…':action==='pause'?'A pausar o alerta…':action==='resume'?'A retomar o alerta…':action==='ack'?'A confirmar o drop…':'A registar o item…';}
  return farmApi(action,name,account).then(function(data){
    window.__FARM_WATCH__={targets:data.targets||[],hits:data.hits||[]};syncFarmButtons(window.__FARM_WATCH__);renderFarmWatchBar(window.__FARM_WATCH__);
    toast((data.message||'Lista de alertas atualizada.')+' — o run.bat mantem a vigia ativa.');return data;
  }).catch(function(error){if(bar){bar.classList.add('show');bar.textContent=error.message||'Nao foi possivel comunicar com o run.bat.';}throw error;});
}
window.farmToggle=function(button){
  if(button.dataset.busy==='1')return;var name=button.getAttribute('data-farm')||'';if(!name)return;
  var account=farmAccountForButton(button).trim().toLowerCase();
  var target=(window.__FARM_WATCH__&&window.__FARM_WATCH__.targets||[]).find(function(item){var wanted=String(item.conta||'').trim().toLowerCase();return String(item.name||'').trim().toLowerCase()===name.trim().toLowerCase()&&(!wanted||!account||wanted===account||account.endsWith('('+wanted+')'));});
  if(target){toast(target.paused?'Este alerta esta em pausa. Usa Retomar ou Parar na lista de alertas.':'Este alerta ja esta na lista. Usa Parar na lista de alertas para o remover.');return;}
  button.dataset.busy='1';button.disabled=true;
  farmAction('add',name,farmAccountForButton(button)).catch(function(){}).finally(function(){button.dataset.busy='';button.disabled=false;});
};
function refreshFarmWatchBar(){
  if(!FARM_API_URL||!window.__TBH_FARM_API_TOKEN__){renderFarmWatchBar(window.__FARM_WATCH__||{targets:[],hits:[]});return;}
  farmApi().then(function(data){window.__FARM_WATCH__={targets:data.targets||[],hits:data.hits||[]};syncFarmButtons(window.__FARM_WATCH__);renderFarmWatchBar(window.__FARM_WATCH__);}).catch(function(){});
}
function renderFarmWatchBar(w){
  var bar=document.getElementById('farmWatchBar');if(!bar||!w)return;
  var targets=w.targets||[],allHits=w.hits||[],pending=allHits.filter(function(hit){return !hit.acknowledged;}),activeCount=targets.filter(function(target){return !target.paused;}).length,pausedCount=targets.length-activeCount;
  if(!targets.length&&!pending.length){bar.classList.remove('show');bar.innerHTML='';return;}
  var html='<h4>🎯 ALERTAS DE FARM — <span style="color:#7ee787">'+activeCount+' a vigiar</span>'+(pausedCount?' · <span style="color:#ffca73">'+pausedCount+' em pausa</span>':'')+' · atualização automática</h4>';
  if(targets.length){
    html+='<div class="fw-tags">';targets.forEach(function(target){
      var name=String(target.name||'?'),account=String(target.conta||''),quantity=0,paused=!!target.paused;
      allHits.forEach(function(hit){var wanted=account.trim().toLowerCase(),actual=String(hit.conta||'').trim().toLowerCase();if(String(hit.name||'').trim().toLowerCase()===name.trim().toLowerCase()&&(!wanted||actual===wanted||actual.endsWith('('+wanted+')')))quantity+=Math.max(0,parseInt(hit.qtd,10)||0);});
      html+='<span class="fw-tag"><b>'+farmEscape(name)+'</b><span style="color:#a89878">'+farmEscape(account?' @ '+account:' @ todas')+' · '+quantity+' encontrada(s)</span>'+(paused?'<span class="fw-paused">⏸ PAUSADO</span>':'')+'<button type="button" data-farm-action="'+(paused?'resume':'pause')+'" data-name="'+farmEscape(name)+'" data-conta="'+farmEscape(account)+'">'+(paused?'▶ Retomar':'⏸ Pausar')+'</button><button type="button" data-farm-action="remove" data-name="'+farmEscape(name)+'" data-conta="'+farmEscape(account)+'" title="Parar remove este item da lista">Parar</button></span>';
    });html+='</div>';}
  pending.slice(-3).forEach(function(hit){var name=String(hit.name||'?'),account=String(hit.conta||'?');html+='<div class="fw-hit">🔔 <b>'+farmEscape(name)+'</b> @ '+farmEscape(account)+' ×'+(parseInt(hit.qtd,10)||1)+' — drop encontrado <button type="button" data-farm-action="ack" data-name="'+farmEscape(name)+'" data-conta="'+farmEscape(account)+'">✓ Confirmar</button></div>';});
  html+='<div style="margin-top:6px;font-size:11px;color:#a89878">Pausar mantém o item guardado sem gerar alertas; Retomar volta a vigiar. Parar remove o item da lista.</div>';
  bar.innerHTML=html;bar.querySelectorAll('[data-farm-action]').forEach(function(button){button.addEventListener('click',function(){button.disabled=true;farmAction(button.dataset.farmAction,button.dataset.name,button.dataset.conta).catch(function(){}).finally(function(){button.disabled=false;});});});bar.classList.add('show');
}
