// === 产业链研究工作台 — 全局 JavaScript ===

// 全局搜索
const searchInput = document.getElementById('globalSearch');
const searchResults = document.getElementById('searchResults');

if (searchInput) {
    let searchTimeout;
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        const q = searchInput.value.trim();
        if (!q) {
            searchResults.classList.remove('has-items');
            searchResults.innerHTML = '';
            return;
        }
        searchTimeout = setTimeout(async () => {
            const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
            const data = await res.json();
            if (data.results.length > 0) {
                searchResults.innerHTML = data.results.map(r => {
                    const statusIcon = {DONE:'✅',WIP:'🔵',TODO:'⬜',GAP:'⚠️',HOLD:'⏸️'}[r.status] || '';
                    return `<a href="/node/${r.id}">${statusIcon} ${r.id} ${r.name}</a>`;
                }).join('');
                searchResults.classList.add('has-items');
            } else {
                searchResults.innerHTML = '<a style="color:#94a3b8">无匹配结果</a>';
                searchResults.classList.add('has-items');
            }
        }, 300);
    });

    // 点击外部关闭搜索结果
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-box')) {
            searchResults.classList.remove('has-items');
        }
    });

    // 回车跳转第一个结果
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const first = searchResults.querySelector('a[href]');
            if (first) first.click();
        }
    });
}

// 全局工具函数
function formatDate(d) {
    return d ? d : '-';
}

function statusBadge(status) {
    const map = {
        DONE: '<span class="badge badge-done">✅ 已完成</span>',
        WIP: '<span class="badge badge-wip">🔵 研究中</span>',
        TODO: '<span class="badge badge-todo">⬜ 未开始</span>',
        GAP: '<span class="badge badge-gap">⚠️ 待补充</span>',
        HOLD: '<span class="badge badge-hold">⏸️ 暂缓</span>',
    };
    return map[status] || status;
}
