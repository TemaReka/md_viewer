/* All content is local to the published snapshot. No requests to the user's PC. */
const $ = id => document.getElementById(id);
const key = 'ddia-cards-v1';
let cards = [], folders = [], selected = new Set(), visible = [], current = null;
let saved = {};
try { saved = JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch {}
function persist() {
  try { localStorage.setItem(key, JSON.stringify({folders:[...selected], card:current?.id, search:$('search').value})); } catch {}
}
function hashId() { try { return decodeURIComponent(location.hash.slice(1)); } catch { return ''; } }
function folderLabel(path) { return path.replace(/\/questions$/, '').replaceAll('/', ' / '); }
function renderFolders() {
  $('folders').replaceChildren(...folders.map(folder => {
    const label = document.createElement('label'); label.className = 'folder';
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = selected.has(folder);
    checkbox.addEventListener('change', () => { checkbox.checked ? selected.add(folder) : selected.delete(folder); filter(); });
    const name = document.createElement('span'); name.className = 'folder-name'; name.textContent = folderLabel(folder);
    const count = document.createElement('span'); count.className = 'folder-count'; count.textContent = cards.filter(c => c.folder === folder).length;
    label.append(checkbox, name, count); return label;
  }));
}
function filter(preferred) {
  const query = $('search').value.trim().toLocaleLowerCase('ru');
  visible = cards.filter(c => selected.has(c.folder) && (!query || (c.title+'\n'+c.markdown).toLocaleLowerCase('ru').includes(query)));
  $('collection-count').textContent = `Найдено заметок: ${visible.length} из ${cards.length}`;
  show(visible.find(c => c.id === preferred) || visible.find(c => c.id === current?.id) || visible[0]);
}
function show(card, scroll = false) {
  current = card || null;
  const article = $('card'); article.setAttribute('aria-busy','false');
  $('navigation').hidden = !card;
  if (!card) {
    article.innerHTML = '<div class="empty"><h1>Здесь пока тихо.</h1><p>Выберите папки или измените поисковый запрос.</p></div>';
    $('position').textContent = '0 заметок'; $('card-meta').textContent = '';
    history.replaceState(null,'',location.pathname+location.search); persist(); return;
  }
  const index = visible.indexOf(card);
  $('position').textContent = `${index+1} / ${visible.length}`;
  $('card-meta').textContent = `${folderLabel(card.folder)}  ·  ${Math.max(1,Math.ceil(card.markdown.split(/\s+/).length/180))} мин чтения`;
  article.innerHTML = DOMPurify.sanitize(marked.parse(card.markdown, {gfm:true}));
  for (const p of article.querySelectorAll('p')) {
    const first = p.firstChild;
    if (first?.nodeType !== Node.TEXT_NODE) continue;
    const match = first.textContent.match(/^(Context|U|A):\s*/);
    if (!match) continue;
    first.textContent = first.textContent.slice(match[0].length);
    const label = document.createElement('span'); label.className='dialogue-label';
    label.textContent = {Context:'КОНТЕКСТ',U:'ВОПРОС',A:'ОТВЕТ'}[match[1]];
    p.prepend(label); if (match[1] === 'Context') p.classList.add('context'); if (match[1] === 'U') p.classList.add('question');
  }
  for (const table of article.querySelectorAll('table')) {
    const wrapper=document.createElement('div'); wrapper.className='table-scroll'; wrapper.tabIndex=0; wrapper.setAttribute('role','region'); wrapper.setAttribute('aria-label','Таблица с горизонтальной прокруткой'); table.replaceWith(wrapper); wrapper.append(table);
  }
  for (const a of article.querySelectorAll('a[href]')) {
    const target = a.getAttribute('href');
    if (target.startsWith('#card:')) {
      const id = target.slice(6); a.href = '#'+encodeURIComponent(id);
      a.addEventListener('click', e => {
        e.preventDefault(); const linked=cards.find(c=>c.id===id); if (!linked) return;
        selected.add(linked.folder); $('search').value=''; renderFolders(); filter(id); window.scrollTo({top:0});
      });
    } else if (/^https?:/i.test(target)) { a.target='_blank'; a.rel='noopener noreferrer'; }
  }
  for (const img of article.querySelectorAll('img')) img.loading='lazy';
  $('prev').disabled=index===0; $('next').disabled=index===visible.length-1; $('random').disabled=visible.length<2;
  history.replaceState(null,'','#'+encodeURIComponent(card.id)); document.title=card.title+' · На полях'; persist();
  if(scroll) window.scrollTo({top:Math.max(0,$('card-meta').getBoundingClientRect().top+window.scrollY-20)});
}
$('prev').onclick=()=>show(visible[visible.indexOf(current)-1],true);
$('next').onclick=()=>show(visible[visible.indexOf(current)+1],true);
$('random').onclick=()=>{ if(visible.length<2)return; const index=visible.indexOf(current); let next=Math.floor(Math.random()*(visible.length-1)); if(next>=index)next++; show(visible[next],true); };
$('search').addEventListener('input',()=>filter());
$('select-all').onclick=()=>{ selected=new Set(folders); renderFolders(); filter(); };
function toggleFolders() { const isOpen=$('library').classList.toggle('open'); $('folders-toggle').setAttribute('aria-expanded',String(isOpen)); }
$('folders-toggle').onclick=toggleFolders;
$('folders-toggle').setAttribute('aria-expanded','false');
window.addEventListener('hashchange',()=>{const linked=cards.find(c=>c.id===hashId()); if(linked){selected.add(linked.folder);$('search').value='';renderFolders();filter(linked.id);}});
document.addEventListener('keydown', e=>{if(/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)||e.altKey||e.ctrlKey||e.metaKey)return; if(e.key==='ArrowLeft'&&!$('prev').disabled&&current)$('prev').click();if(e.key==='ArrowRight'&&!$('next').disabled&&current)$('next').click();});
async function loadLibrary(selectNew = false) {
  try {
    const previousFolders = new Set(folders);
    const previousCard = current?.id;
    try { saved = JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch {}
    const response=await fetch('cards.json',{cache:'no-store'}); if(!response.ok)throw Error(response.status);
    const data=await response.json(); cards=data.cards; folders=[...new Set(cards.map(c=>c.folder))];
    selected=new Set(Array.isArray(saved.folders)?saved.folders.filter(f=>folders.includes(f)):folders);
    if (selectNew) for (const folder of folders) if (!previousFolders.has(folder)) selected.add(folder);
    $('search').value=typeof saved.search==='string'?saved.search:'';
    const requested=cards.find(c=>c.id===hashId()); if(requested){selected.add(requested.folder);$('search').value='';}
    $('updated').textContent='Обновлено '+new Date(data.updated).toLocaleDateString('ru-RU');
    renderFolders(); filter(requested?.id || previousCard || saved.card);
  } catch(error) { $('card').textContent='Не удалось открыть заметки. Проверьте подключение и обновите страницу.'; $('card').setAttribute('aria-busy','false'); console.error(error); }
}
loadLibrary();

// Management is available only in the local process started by manage.cmd.
if (location.hostname === '127.0.0.1') {
  let managerToken = '', wasBusy = false;
  async function refreshManager() {
    const response = await fetch('/api/state', {cache:'no-store'});
    if (!response.ok) throw Error('Локальное управление недоступно. Запустите manage.cmd.');
    const state = await response.json();
    managerToken = state.token;
    $('manage-help').hidden = true;
    $('manage-actions').hidden = false;
    $('source-controls').open = true;
    $('manage-status').textContent = state.message;
    $('source-list').replaceChildren(...state.directories.map((path, index) => {
      const item = document.createElement('li');
      const name = document.createElement('span'); name.textContent = path;
      const remove = document.createElement('button'); remove.className = 'text-button';
      remove.textContent = 'Убрать'; remove.disabled = state.busy;
      remove.setAttribute('aria-label', 'Убрать папку '+path);
      remove.onclick = () => command('remove', {index});
      item.append(name, remove); return item;
    }));
    $('add-source').disabled = $('publish-sources').disabled = state.busy;
    if (wasBusy && !state.busy) await loadLibrary(true);
    wasBusy = state.busy;
    if (state.busy) setTimeout(() => refreshManager().catch(managementError), 1000);
  }
  function managementError(error) {
    $('manage-status').textContent = error.message;
    $('add-source').disabled = $('publish-sources').disabled = false;
  }
  async function command(action, data = {}) {
    $('add-source').disabled = $('publish-sources').disabled = true;
    try {
      const response = await fetch('/api/'+action, {method:'POST',
        headers:{'Content-Type':'application/json', 'X-Cards-Token':managerToken}, body:JSON.stringify(data)});
      if (!response.ok) { const result = await response.json(); throw Error(result.error); }
      wasBusy = true;
      await refreshManager();
    } catch (error) { managementError(error); }
  }
  $('add-source').onclick = () => command('choose');
  $('publish-sources').onclick = () => command('publish');
  refreshManager().catch(() => {});
}
