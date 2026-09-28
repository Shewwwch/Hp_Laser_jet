const $ = (selector) => document.querySelector(selector);
let mode = 'demo';
let current = null;
const params = new URLSearchParams(location.search);

function el(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) node.textContent = String(value);
  return node;
}

function message(value, error = false) {
  $('#message').textContent = value;
  $('#message').classList.toggle('error', error);
}

function setMode(value) {
  mode = value;
  document.querySelectorAll('.mode').forEach(btn => btn.classList.toggle('selected', btn.dataset.mode === value));
  $('#mode-note').textContent = value === 'live'
    ? 'Живой запрос к OpenAlex; обычно занимает несколько секунд'
    : 'Проверяемая подборка из предоставленной таблицы';
}

async function search(refresh = false) {
  const q = $('#query').value.trim();
  if (q.length < 2) { message('Введите хотя бы два символа.', true); return; }
  $('#search-button').disabled = true;
  $('#search-button').firstChild.textContent = 'Ищем… ';
  message(mode === 'live' ? 'Получаем научные публикации и сравниваем временные выборки…' : 'Считаем сигналы…');
  try {
    const url = `/api/search?q=${encodeURIComponent(q)}&mode=${mode}${refresh ? '&refresh=1' : ''}`;
    const response = await fetch(url);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Ошибка ${response.status}`);
    current = data;
    render(data);
    const state = new URLSearchParams({q, mode});
    history.replaceState(null, '', `${location.pathname}?${state}`);
    message('');
    if (location.hash.startsWith('#trend-')) {
      const id = decodeURIComponent(location.hash.slice(7));
      if (data.results.some(item => item.id === id)) openReport(id);
    }
  } catch (error) { message(error.message, true); }
  finally { $('#search-button').disabled = false; $('#search-button').firstChild.textContent = 'Найти сигналы '; }
}

function render(data) {
  $('#candidate-count').textContent = data.candidate_count;
  $('#source-count').textContent = data.source_count;
  $('#result-count').textContent = data.results.length;
  $('#strong-count').textContent = data.results.filter(item => item.score >= 75).length;
  document.querySelector('#strong-count').nextElementSibling.textContent = data.mode === 'live' && data.results.some(item => item.score_label === 'Оценка классификатора') ? 'оценка обученной модели' : 'не вероятность модели';
  $('#top-badge').textContent = `ТОП ${data.results.length}`;
  $('#result-description').textContent = `${data.coverage} ${data.cached ? 'Показан сохранённый результат.' : ''}`;
  const list = $('#results-list'); list.replaceChildren();
  if (!data.results.length) list.append(el('div', 'empty', 'Подтверждённых кандидатов по этому запросу пока нет. Попробуйте расширить тему или сменить источник данных.'));
  data.results.forEach((item, index) => {
    const button = el('button', 'result'); button.type = 'button';
    button.setAttribute('aria-label', `Открыть аналитическую записку: ${item.title}`);
    const first = el('div');
    first.append(el('span', 'main-title', `${String(index + 1).padStart(2, '0')}  ${item.title}`), el('span', 'summary', item.explanation[0]));
    button.append(first, el('span', 'area', item.area), el('span', 'score', item.score), el('span', 'arrow', '↗'));
    button.addEventListener('click', () => openReport(item.id));
    list.append(button);
  });
  const excluded = $('#excluded-list'); excluded.replaceChildren();
  if (!data.excluded.length) excluded.append(el('span', 'subtle', data.mode === 'demo' ? 'Для редакционной подборки исходный файл не содержит исключённых технологий.' : 'В этой выборке исключённых кандидатов не обнаружено.'));
  data.excluded.slice(0, 12).forEach(item => {
    const tag = el('div', 'exclusion', item.title);
    tag.append(el('span', '', item.reason)); excluded.append(tag);
  });
}

function section(root, title, content) {
  const wrapper = el('section', 'report-section');
  wrapper.append(el('h3', '', title));
  wrapper.append(el('p', '', content || 'Не указано в источнике.'));
  root.append(wrapper);
}

function openReport(id) {
  const item = current?.results.find(result => result.id === id);
  if (!item) return;
  const body = el('div', 'report-body');
  body.append(el('div', 'eyebrow', current.mode === 'demo' ? 'РЕДАКЦИОННАЯ ПОДБОРКА / СЕНТЯБРЬ 2026' : 'ОТКРЫТЫЕ НАУЧНЫЕ ИСТОЧНИКИ'));
  body.append(el('h2', '', item.title));
  body.append(el('div', 'report-meta', `${item.area} · ${item.stage} · ${current.updated_at || ''}`));
  const score = el('div', 'report-score'); score.append(el('strong', '', item.score), el('span', '', `${item.score_label} / 100`)); body.append(score);
  body.append(el('div', 'report-note', `${current.score_note} ${item.basis}`));
  section(body, 'Что обнаружено', item.description);
  section(body, 'Проблема и потенциальное преимущество', item.advantage);
  section(body, 'Кейс / кто исследует', item.case);
  section(body, 'Почему это ранний сигнал', item.momentum);
  const factors = el('section', 'report-section'); factors.append(el('h3', '', 'Признаки и ограничения'));
  const ul = el('ul'); item.explanation.forEach(factor => ul.append(el('li', '', factor))); factors.append(ul); body.append(factors);
  const sources = el('section', 'report-section'); sources.append(el('h3', '', `Источники (${item.sources.length})`));
  item.sources.forEach(source => {
    const row = el('div', 'source');
    if (source.url && /^https?:\/\//.test(source.url)) {
      const link = el('a', '', source.title); link.href = source.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; row.append(link);
    } else row.append(el('b', '', source.title));
    row.append(el('small', '', `${source.date || 'дата не указана'} · ${source.type} · язык: ${source.language} · доверие: ${source.trust}`));
    row.append(el('small', '', source.note)); sources.append(row);
  }); body.append(sources);
  $('#report-content').replaceChildren(body);
  $('#report-backdrop').hidden = false;
  document.body.style.overflow = 'hidden';
  location.hash = `trend-${encodeURIComponent(id)}`;
  $('#close-report').focus();
}

function closeReport() {
  $('#report-backdrop').hidden = true;
  document.body.style.overflow = '';
  history.replaceState(null, '', location.pathname + location.search);
}

$('#search-form').addEventListener('submit', event => {event.preventDefault(); search();});
document.querySelectorAll('.mode').forEach(btn => btn.addEventListener('click', () => {setMode(btn.dataset.mode); search();}));
$('#close-report').addEventListener('click', closeReport);
$('#print-report').addEventListener('click', () => window.print());
$('#report-backdrop').addEventListener('click', event => {if (event.target.id === 'report-backdrop') closeReport();});
document.addEventListener('keydown', event => {if (event.key === 'Escape' && !$('#report-backdrop').hidden) closeReport();});
if (params.has('q')) $('#query').value = params.get('q');
if (params.get('mode') === 'live') setMode('live');
search();
