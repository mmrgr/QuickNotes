const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const HTML_PATH = 'C:/Users/mmrgr/WorkBuddy/2026-10-02-07-54-58/notes-market/index.html';
const html = fs.readFileSync(HTML_PATH, 'utf8');

// 打桩：构造 25 条记录，验证分页（PAGE_SIZE=9 → 3 页）
function makeRows(n) {
  const rows = [];
  for (let i = 1; i <= n; i++) {
    rows.push({
      record_id: 'rec_' + i,
      '标题': '便签集 ' + i,
      '作者': '用户' + (i % 4),
      '简介': '这是第 ' + i + ' 个分享包的简介',
      '分享内容': JSON.stringify({ type: 'quicknotes-share', version: 1, notes: [{ text: 'n' + i }] }),
      '便签数量': i,
      '下载次数': i * 2,
      '上传时间': '2026-10-0' + ((i % 9) + 1) + 'T0' + (i % 9) + ':00:00.000Z'
    });
  }
  return rows;
}

const ROWS = makeRows(25);
const calls = { query: 0, addRecord: 0, updateRecord: 0 };

const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost/',
  beforeParse(win) {
    win.__SMART_PAGE__ = {
      database: {
        query(params) {
          calls.query++;
          const pageSize = params.pageSize || 50;
          const start = params.startCursor ? Number(params.startCursor) : 0;
          const slice = ROWS.slice(start, start + pageSize);
          const next = start + slice.length;
          return Promise.resolve({
            results: slice,
            nextCursor: next < ROWS.length ? String(next) : '',
            hasMore: next < ROWS.length
          });
        },
        addRecord(params) { calls.addRecord++; return Promise.resolve({ id: 'new_1' }); },
        updateRecord(params) { calls.updateRecord++; return Promise.resolve({ id: params.recordId }); },
        getSchema() { return Promise.resolve({ properties: [] }); }
      }
    };
  }
});
const win = dom.window;

// 轮询等待渲染完成
let waited = 0;
const timer = setInterval(() => {
  waited += 100;
  const cards = win.document.querySelectorAll('#cards .card');
  const pagerBtns = win.document.querySelectorAll('#pager button');
  if (cards.length > 0 || waited > 4000) {
    clearInterval(timer);

    const results = [];
    const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

    ok('卡片渲染数量 = 9（首页）', cards.length === 9, 'got=' + cards.length);
    ok('统计总数 = 25', win.document.querySelector('.stat-total').textContent === '25',
       'got=' + win.document.querySelector('.stat-total').textContent);
    ok('便签总数 = 325', win.document.querySelector('.stat-pages').textContent === '325',
       'got=' + win.document.querySelector('.stat-pages').textContent);
    ok('query 被调用（分页三保险走通）', calls.query >= 1, 'calls=' + calls.query);
    ok('分页按钮存在', pagerBtns.length > 0, 'btns=' + pagerBtns.length);
    ok('加载态已隐藏', win.document.querySelector('#loading').style.display === 'none');
    ok('首卡标题正确', (cards[0] && cards[0].querySelector('.market-title').textContent) === '便签集 1',
       cards[0] ? cards[0].querySelector('.market-title').textContent : 'none');
    ok('首卡作者正确', (cards[0] && cards[0].querySelector('.market-author').textContent) === '用户1');

    // 测试翻页
    const nextBtn = win.document.querySelector('#pager button[data-pg="next"]');
    if (nextBtn) {
      nextBtn.dispatchEvent(new win.MouseEvent('click', { bubbles: true }));
      const cards2 = win.document.querySelectorAll('#cards .card');
      ok('翻到第 2 页仍有 9 张卡', cards2.length === 9, 'got=' + cards2.length);
      ok('第 2 页首卡标题=便签集 10',
         cards2[0] && cards2[0].querySelector('.market-title').textContent === '便签集 10',
         cards2[0] ? cards2[0].querySelector('.market-title').textContent : 'none');
    }

    // 测试搜索
    const search = win.document.querySelector('#search');
    search.value = '便签集 25';
    search.dispatchEvent(new win.Event('input', { bubbles: true }));
    setTimeout(() => {
      const filtered = win.document.querySelectorAll('#cards .card');
      ok('搜索"便签集 25"命中 1 条', filtered.length === 1, 'got=' + filtered.length);

      // 测试下载（点第一张卡的下载按钮）
      const dlBtn = win.document.querySelector('#cards button[data-act="download"]');
      if (dlBtn) {
        dlBtn.dispatchEvent(new win.MouseEvent('click', { bubbles: true }));
        setTimeout(() => {
          ok('下载触发 updateRecord 计数', calls.updateRecord >= 1, 'calls=' + calls.updateRecord);

          console.log('\n===== 测试结果 =====');
          let passCount = 0;
          results.forEach(r => {
            console.log((r.pass ? 'PASS' : 'FAIL') + '  ' + r.name + (r.extra ? '  (' + r.extra + ')' : ''));
            if (r.pass) passCount++;
          });
          console.log('\n通过 ' + passCount + '/' + results.length);
          dom.window.close();
          process.exit(passCount === results.length ? 0 : 1);
        }, 200);
      } else {
        console.log('未找到下载按钮');
        process.exit(1);
      }
    }, 400);
  }
}, 100);
