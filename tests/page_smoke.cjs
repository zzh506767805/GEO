#!/usr/bin/env node
// 不用浏览器，把工作台和体检报告都渲染一遍，检查有没有报错、有没有把 undefined / NaN 显示给商家。
//
//   node tests/page_smoke.cjs <工作台或报告.html> [更多.html ...]
//
// 做法：给页面脚本一个最小的假 DOM。工作台依次切到每个页面（包括“在工作台里打开某一期报告”）；
// 报告是独立的文件，按“单独打开”和“嵌在工作台里”两种方式各渲染一遍。然后把页面上能点的东西都点一遍。
// 它查不了样式和排版（那要真浏览器），但能拦住“模板用了数据里没有的字段”这一类错误。
// 输出一行 JSON：{"ok": true/false, "files": [{file, kind, pages, routes, frames, errors}]}
// frames 是工作台里嵌报告时用的地址；报告的 embedded 说明嵌进去时有没有去掉自己的标题。
'use strict';
const fs = require('node:fs');
const vm = require('node:vm');

const BAD_TEXT = /undefined|NaN|\[object |null 次|null 处|null 条/;

function makeNode(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], attrs: {}, style: {}, parentNode: null,
    _text: '', className: '', hidden: false, disabled: false,
    appendChild(child) {
      if (child && child.tagName === '#FRAGMENT') { child.children.slice().forEach((c) => node.appendChild(c)); child.children = []; return child; }
      if (child.parentNode) { child.parentNode.removeChild(child); }
      child.parentNode = node; node.children.push(child); return child;
    },
    removeChild(child) { node.children = node.children.filter((c) => c !== child); child.parentNode = null; return child; },
    setAttribute(key, value) { node.attrs[key] = String(value); },
    getAttribute(key) { return node.attrs[key]; },
    focus() {}, select() {}, scrollIntoView() {},
  };
  Object.defineProperty(node, 'textContent', {
    get() { return node._text + node.children.map((c) => c.textContent).join(''); },
    set(value) { node.children.forEach((c) => { c.parentNode = null; }); node.children = []; node._text = String(value); },
  });
  Object.defineProperty(node, 'firstChild', { get() { return node.children[0] || null; } });
  return node;
}

function walk(node, visit) { visit(node); node.children.slice().forEach((child) => walk(child, visit)); }
// 页面上我们自己拼出来的文字。AI 回答的正文（ans-text）是别人写的原话，不算在内。
function ownText(node) {
  if (/\bans-text\b/.test(node.className || '')) { return ''; }
  return node._text + node.children.map(ownText).join('');
}

function check(file) {
  const html = fs.readFileSync(file, 'utf8');
  const data = /<script type="application\/json" id="geo-data">([\s\S]*?)<\/script>/.exec(html);
  const code = /<script>\s*([\s\S]*?)<\/script>\s*<\/body>/.exec(html);
  if (!data || !code) { return { file, kind: '', pages: 0, errors: ['找不到数据块或页面脚本'] }; }
  const kind = JSON.parse(data[1]).kind === 'report' ? 'report' : 'workbench';
  if (kind === 'workbench') { return render(file, kind, data[1], code[1], ''); }
  // 报告：单独打开一遍，嵌在工作台里再来一遍（地址带 #embed，可以直接到某一节）
  const alone = render(file, kind, data[1], code[1], '');
  const inside = render(file, kind, data[1], code[1], '#embed/mentions');
  const errors = alone.errors.concat(inside.errors.map((e) => '嵌在工作台里时 ' + e));
  if (!/体检报告/.test(alone.head)) { errors.push('单独打开时没有标题'); }
  if (inside.head) { errors.push('嵌在工作台里时还带着自己的标题：' + inside.head.slice(0, 30)); }
  if (inside.said !== 'report-ready') { errors.push('嵌在工作台里时没有跟外面打招呼'); }
  return { file, kind, pages: 1, routes: [], embedded: !inside.head, errors };
}

function render(file, kind, dataText, codeText, startHash) {
  const errors = [];
  const data = [null, dataText], code = [null, codeText];
  const elements = { 'geo-data': makeNode('script'), app: makeNode('div'), sheet: makeNode('div') };
  elements['geo-data']._text = data[1];
  elements.sheet.appendChild(makeNode('div'));
  elements.sheet.hidden = true;
  const listeners = {};
  const body = makeNode('body');
  const document = {
    title: '', body, activeElement: null,
    getElementById: (id) => elements[id] || null,
    createElement: makeNode, createElementNS: (_ns, tag) => makeNode(tag),
    createTextNode: (text) => { const n = makeNode('#text'); n._text = String(text); return n; },
    createDocumentFragment: () => makeNode('#fragment'),
    addEventListener: (type, fn) => { listeners['doc:' + type] = fn; },
    execCommand: () => true,
  };
  const location = { hash: startHash, protocol: 'https:' };
  let said = '';
  const outer = { postMessage: (message) => { said = message && message.geo; } };
  outer.parent = outer;
  const window = { addEventListener: (type, fn) => { listeners[type] = fn; }, scrollTo() {}, innerWidth: 1280 };
  if (startHash) { window.parent = outer; }  // 嵌在别的页面里
  const sandbox = { document, window, location, navigator: {}, setTimeout: (fn) => { fn(); return 1; }, clearTimeout() {}, console };
  try {
    vm.runInNewContext(code[1], sandbox, { filename: file });
  } catch (error) {
    return { file, kind, pages: 0, errors: ['页面脚本一运行就报错：' + error.message] };
  }
  const links = [];
  walk(elements.app, (node) => { if (node.tagName === 'A' && /^#\//.test(node.href || '')) { links.push(node.href); } });
  const routes = Array.from(new Set(links.map((href) => href.replace(/^#\//, '').split('?')[0])));
  let pages = 0;
  const visit = (hash) => {
    try {
      if (kind === 'workbench') {
        location.hash = hash;
        listeners.hashchange();
      }
      pages += 1;
      // 把能点的都点一遍：筛选按钮、圆点（弹出原话）、可复制的话、页签
      const clickable = [];
      walk(elements.app, (node) => { if (typeof node.onclick === 'function' && node.tagName === 'BUTTON' && !node.disabled) { clickable.push(node); } });
      clickable.slice(0, 400).forEach((node) => node.onclick({ target: node }));
      if (typeof elements.sheet.onclick === 'function') { elements.sheet.onclick({ target: elements.sheet }); }
      const text = ownText(elements.app) + ownText(elements.sheet);
      const bad = BAD_TEXT.exec(text);
      if (bad) { errors.push(hash + '：页面上出现了“' + text.slice(Math.max(0, bad.index - 20), bad.index + 20) + '”'); }
      if (text.length < 40) { errors.push(hash + '：页面几乎是空的'); }
    } catch (error) {
      errors.push(hash + '：' + error.message);
    }
  };
  if (kind === 'report') {
    // 报告脚本一运行就渲染好了；这里只检查内容并把按钮点一遍
    visit(startHash);
    let head = '';
    walk(elements.app, (node) => { if (/\brpt-head\b/.test(node.className || '')) { head = node.textContent; } });
    return { errors, head, said };
  }
  if (!routes.length) { errors.push('侧边栏里没有任何页面链接'); }
  const frames = [];
  let homeText = '', sparkBars = -1;
  routes.forEach((route) => {
    visit('#/' + route);
    if (route === 'overview') {
      // 首页上写了什么、“没点名时提到你”旁边画了几根小柱子（一期一根，只画口径相同的那几期）
      homeText = ownText(elements.app);
      walk(elements.app, (node) => { if (sparkBars < 0 && node.tagName === 'SVG' && node.attrs.class === 'spark') { sparkBars = node.children.filter((n) => n.tagName === 'RECT').length; } });
    }
    if (/^report\//.test(route)) {
      let src = '';
      walk(elements.app, (node) => { if (node.tagName === 'IFRAME') { src = node.src || ''; } });
      if (!src) { errors.push('#/' + route + '：没有把报告嵌进来'); } else { frames.push(src); }
      if (typeof listeners.message === 'function') { listeners.message({ data: { geo: 'report-ready' } }); }
    }
  });
  visit('#/not-a-page');
  return { file, kind, pages, routes, frames, homeText, sparkBars: Math.max(sparkBars, 0), errors };
}

const files = process.argv.slice(2);
if (!files.length) { console.error('用法：node page_smoke.cjs <工作台.html> ...'); process.exit(2); }
const results = files.map(check);
const ok = results.every((r) => r.errors.length === 0);
console.log(JSON.stringify({ ok, files: results }));
process.exit(ok ? 0 : 1);
