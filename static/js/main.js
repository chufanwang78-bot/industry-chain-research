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
            const res = await fetch(`/api/${encodeURIComponent(PROJECT)}/search?q=${encodeURIComponent(q)}`);
            const data = await res.json();
            if (data.results.length > 0) {
                searchResults.innerHTML = data.results.map(r => {
                    const statusIcon = {DONE:'✅',WIP:'🔵',TODO:'⬜',GAP:'⚠️',HOLD:'⏸️'}[r.status] || '';
                    return `<a href="/${encodeURIComponent(PROJECT)}/node/${r.id}">${statusIcon} ${r.id} ${r.name}</a>`;
                }).join('');
                searchResults.classList.add('has-items');
            } else {
                searchResults.innerHTML = '<a style="color:#94a3b8">无匹配结果</a>';
                searchResults.classList.add('has-items');
            }
        }, 300);
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-box')) {
            searchResults.classList.remove('has-items');
        }
    });

    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const first = searchResults.querySelector('a[href]');
            if (first) first.click();
        }
    });
}
