// 全域變數儲存資料
let allVegetables = [];
let vegetables = [];
let recipes = [];
let vegNameMapping = {};
let chartInstances = {}; // 用於存儲圖表實例

// DOM 元素
const menuToggle = document.getElementById('menuToggle');
const sidebar = document.getElementById('sidebar');
const navItems = document.querySelectorAll('.nav-item');
const contentSections = document.querySelectorAll('.content-section');
const chatToggle = document.getElementById('chatToggle');
const chatBody = document.getElementById('chatBody');
const chatInput = document.getElementById('chatInput');
const sendMessage = document.getElementById('sendMessage');
const chatMessages = document.getElementById('chatMessages');
const uploadBtn = document.getElementById('uploadBtn');
const imageUpload = document.getElementById('imageUpload');
const vegetableTagsContainer = document.querySelector('.vegetable-tags-container');
const recipeGrid = document.getElementById('recipeGrid');
const seasonFilterContainer = document.getElementById('seasonFilter');
const vegetableGrid = document.getElementById('vegetableGrid');
const priceResults = document.getElementById('priceResults');

// 初始化
document.addEventListener('DOMContentLoaded', async function () {
    setupEventListeners();
    await initializeApp();
});

function getQueryParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

function filterBySeason(vegetables, season) {
    if (!season || season === 'all') {
        return vegetables; // 如果季節是 'all' 或不存在，回傳全部蔬菜
    }
    // 將英文參數轉換為後端使用的中文字串
    const seasonMapping = {
        spring: '春季',
        summer: '夏季',
        autumn: '秋季',
        winter: '冬季'
    };
    const chineseSeason = seasonMapping[season.toLowerCase()];
    if (!chineseSeason) {
        console.warn('無效的季節參數:', season);
        return vegetables; // 如果參數無效，回傳所有蔬菜
    }
    // 修改此處的篩選邏輯，支援多季節
    return vegetables.filter(v => {
        // 如果 v.season 是字串，檢查它是否包含被篩選的季節
        if (typeof v.season === 'string') {
            return v.season.includes(chineseSeason);
        }
        // 如果 v.season 是陣列，檢查陣列中是否包含被篩選的季節
        if (Array.isArray(v.season)) {
            return v.season.includes(chineseSeason);
        }
        // 如果都不是，則不匹配
        return false;
    });
}


function updateSeasonFilterButtons(activeSeason) {
    const buttons = seasonFilterContainer.querySelectorAll('.season-filter-btn');
    buttons.forEach(button => {
        if (button.dataset.season === activeSeason) {
            button.classList.add('active');
        } else {
            button.classList.remove('active');
        }
    });
}


async function initializeApp() {
    try {
        const response = await fetch('/api/vegetables');
        if (!response.ok) throw new Error('無法取得蔬菜資料');
        allVegetables = await response.json(); // 正確賦值給全域變數

        const seasonParam = getQueryParam('season') || 'all';
        vegetables = filterBySeason(allVegetables, seasonParam); // 根據 URL 參數或預設值篩選

        updateSeasonFilterButtons(seasonParam); // 更新按鈕狀態

        // 使用篩選後的資料渲染畫面
        renderVegetables();
        renderPricePredictions();

        await fetchVegetableTags();
        if (allVegetables.length > 0) {
            const firstVegId = allVegetables[0].id;
            document.querySelector(`.vegetable-tag[data-id="${firstVegId}"]`)?.classList.add('active');
            await fetchRecipesByVegId(firstVegId);
        }

        renderPageBasedOnUrl();

    } catch (error) {
        console.error('應用程式初始化失敗:', error);
        // 可在此處顯示錯誤訊息給使用者
    }
}



function renderPageBasedOnUrl() {
    const params = new URLSearchParams(window.location.search);
    const section = params.get('section');
    const id = params.get('id');

    if (section === 'detail' && id) {
        showVegetableDetail(id, false);
    } else if (section === 'recipe' && id) {
        // 改成直接抓單一食譜資料
        fetch(`/api/recipe/${id}`)
            .then(res => {
                if (!res.ok) throw new Error('無法取得食譜資料');
                return res.json();
            })
            .then(recipe => {
                showSingleRecipeDetail(recipe); // 新增函式
            })
            .catch(err => {
                console.error('載入食譜失敗:', err);
                showSection('recipe', false);
            });
    } else if (section) {
        showSection(section, false);
    } else {
        showSection('overview', false);
    }
}


// 優化 popstate 事件處理
window.addEventListener('popstate', (event) => {
    renderPageBasedOnUrl();
});

function showSection(targetId, pushState = true) {
    document.getElementById('detailPage')?.remove();
    contentSections.forEach(section => {
        section.classList.remove('active');
    });
    navItems.forEach(nav => {
        nav.classList.remove('active');
    });

    const targetSection = document.getElementById(targetId);
    if (targetSection) {
        targetSection.classList.add('active');
        const correspondingNavItem = document.querySelector(`.nav-item[data-target="${targetId}"]`);
        if (correspondingNavItem) {
            correspondingNavItem.classList.add('active');
        }
    }
    if (pushState) {
        const currentSeason = document.querySelector('.season-filter-btn.active')?.dataset.season || 'all';
        let newUrl = `/?section=${targetId}`;
        // 如果在總覽頁且有季節篩選，則保留參數
        if (targetId === 'overview' && currentSeason !== 'all') {
            newUrl += `&season=${currentSeason}`;
        }
        history.pushState({ target: targetId }, '', newUrl);
    }
    if (window.innerWidth <= 768) sidebar.classList.remove('active');
    window.scrollTo(0, 0);
}

// 讀取蔬菜名稱對照表 (修改為 Promise 函式)
async function loadVegNameMapping() {
    try {
        const response = await fetch('/api/csv/veg_name.csv');
        const csvText = await response.text();
        const lines = csvText.split('\n');

        // 修正重點：移除跳過第一行的條件判斷
        // 現在程式碼會從 index=0 的第一行開始處理
        lines.forEach((line, index) => {
            if (!line.trim()) return; // 只跳過空行
            const [chinese, english] = line.split(',');
            if (chinese && english) {
                vegNameMapping[chinese.trim()] = english.trim();
            }
        });

        // 這裡可以保留之前的偵錯程式碼，以確認所有資料都已正確載入
        console.log('--- 開始檢查 vegNameMapping ---');
        console.log('讀取到的蔬菜數量:', Object.keys(vegNameMapping).length);
        console.log('讀取到的蔬菜名稱對照表:', vegNameMapping);
        console.log('--- 檢查結束 ---');

        generateVegetablesData();
    } catch (error) {
        console.error('載入蔬菜名稱對照表失敗:', error);
        // 如果載入失敗，使用預設值
        vegNameMapping = { '大白菜': 'Chinese Cabbage', '青江菜': 'Bok Choy', '空心菜': 'Water Spinach', '地瓜葉': 'Sweet Potato Leaves', '番茄': 'Tomato', '黃瓜': 'Cucumber' };
        generateVegetablesData();
    }
}


// 新增函式：根據 pageId 顯示對應的內容區塊
function showPage(pageId) {
    // 隱藏所有內容區塊
    contentSections.forEach(section => section.classList.remove('active'));

    // 顯示指定 id 的內容區塊
    const targetPage = document.getElementById(pageId);
    if (targetPage) {
        targetPage.classList.add('active');
        // 如果是食譜頁面，重新載入蔬菜標籤和食譜
        if (pageId === 'recipe-page') {
            initializeApp();
        }
    }
}

// 解析CSV行
function parseCSVLine(line) {
    const result = [];
    let current = '', inQuotes = false;
    for (const char of line) {
        if (char === '"') inQuotes = !inQuotes;
        else if (char === ',' && !inQuotes) { result.push(current.trim()); current = ''; }
        else current += char;
    }
    result.push(current.trim());
    return result;
}

// 生成蔬菜假資料
function generateVegetablesData() {
    const vegNames = Object.keys(vegNameMapping);
    const seasons = ['春季', '夏季', '秋季', '冬季', '四季'];
    vegetables = vegNames.map((name, index) => {
        const basePrice = 20 + Math.random() * 40;
        const priceHistory = Array.from({ length: 30 }, (_, i) => Math.max(10, Math.round(basePrice + (Math.random() - 0.5) * (15 - i * 0.4))));
        const currentPrice = priceHistory[priceHistory.length - 1];
        const previousPrice = priceHistory[priceHistory.length - 2];
        const priceChange = ((currentPrice - previousPrice) / previousPrice * 100).toFixed(1);

        return {
            id: index + 1, name, image: `/api/image/${name}.jpg`, description: `新鮮${name}，營養豐富，是您餐桌上的最佳選擇。`,
            // === 修改：移除假的營養數據，改為空物件，與 API 總覽頁的結構保持一致 ===
            nutrition: {},
            // === 修改結束 ===
            priceHistory, currentPrice, priceChange: `${priceChange >= 0 ? '+' : ''}${priceChange}%`, season: seasons[Math.floor(Math.random() * seasons.length)],
        };
    });
    renderVegetables();
    renderPricePredictions();
}

// 渲染蔬菜總覽卡片
function renderVegetables() {
    if (!vegetableGrid) return;
    vegetableGrid.innerHTML = vegetables.map(veg => `
        <div class="vegetable-card" onclick="showVegetableDetail(${veg.id}, true)" data-name="${veg.name.toLowerCase()}">
            <img src="${veg.image}" alt="${veg.name}" loading="lazy">
            <div class="card-content">
                <h3>${veg.name}</h3>
                <p>${veg.description}</p>
                <div class="price-info">
                    <span class="current-price">NT$ ${veg.currentPrice}</span>
                    <span class="price-change ${veg.priceChange.includes('+') ? 'increase' : 'decrease'}">
                        ${veg.priceChange}
                    </span>
                </div>
            </div>
        </div>
    `).join('');
}

// 渲染價格預測頁面
function renderPricePredictions() {
    if (!priceResults) return;
    priceResults.innerHTML = vegetables.map(veg => `
        <div class="price-card" data-name="${veg.name.toLowerCase()}">
            <div class="price-card-info">
                <img src="${veg.image}" alt="${veg.name}" loading="lazy">
                <div class="price-card-details">
                    <h3>${veg.name}</h3>
                    <div class="price-info">
                        <span>當前價格: NT$ ${veg.currentPrice}</span>
                        <span class="${veg.priceChange.includes('+') ? 'increase' : 'decrease'}">${veg.priceChange}</span>
                    </div>
                </div>
            </div>
            <div class="price-card-chart-container">
                 <div class="time-select">
                    <button onclick="updatePriceChart(event, 'price-page-chart-${veg.id}', ${veg.id}, 7, this)">近7天</button>
                    <button onclick="updatePriceChart(event, 'price-page-chart-${veg.id}', ${veg.id}, 14, this)">近14天</button>
                    <button class="active" onclick="updatePriceChart(event, 'price-page-chart-${veg.id}', ${veg.id}, 30, this)">近30天</button>
                 </div>
                <div class="price-card-chart">
                    <canvas id="price-page-chart-${veg.id}"></canvas>
                </div>
            </div>
        </div>
    `).join('');

    setTimeout(() => {
        vegetables.forEach(veg => {
            updatePriceChart(null, `price-page-chart-${veg.id}`, veg.id, 30);
        });
    }, 100);
}

// 通用的圖表更新函式
function updatePriceChart(event, canvasId, vegId, days, btnElement = null) {
    if (event) event.stopPropagation();
    // 修改：從 allVegetables 裡找，確保無論當前篩選如何，都能找到正確蔬菜的歷史資料
    const vegetable = allVegetables.find(v => v.id === vegId);
    if (!vegetable) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    if (btnElement) {
        btnElement.parentElement.querySelectorAll('button').forEach(btn => btn.classList.remove('active'));
        btnElement.classList.add('active');
    }

    const history = vegetable.priceHistory;
    const data = history.slice(Math.max(0, history.length - days));
    const labels = Array.from({ length: data.length }, (_, i) => `前${data.length - i}天`);
    renderLineChart(canvas, labels, data, '價格', false);
}

// Chart.js 渲染線圖
function renderLineChart(canvas, labels, data, label, showLegend = true) {
    const chartId = canvas.id;
    if (chartInstances[chartId]) chartInstances[chartId].destroy();
    chartInstances[chartId] = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { labels, datasets: [{ label, data, borderColor: '#80c96a', backgroundColor: 'rgba(128, 201, 106, 0.1)', borderWidth: 2, fill: true, tension: 0.4, pointRadius: 2, pointBackgroundColor: '#80c96a' }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: showLegend } }, scales: { y: { beginAtZero: false, ticks: { font: { size: 10 } } }, x: { ticks: { font: { size: 10 }, maxRotation: 0, minRotation: 0, callback: function (value, index) { if (labels.length > 15 && index % 3 !== 0) return ''; return this.getLabelForValue(value); } } } } }
    });
}

// Chart.js 渲染雷達圖
function renderRadarChart(canvas, labels, data, label) {
    const chartId = canvas.id;
    if (chartInstances[chartId]) chartInstances[chartId].destroy();
    chartInstances[chartId] = new Chart(canvas.getContext('2d'), {
        type: 'radar',
        data: { labels, datasets: [{ label, data, backgroundColor: 'rgba(128, 201, 106, 0.2)', borderColor: '#80c96a', pointBackgroundColor: '#80c96a', pointBorderColor: '#fff', pointHoverBackgroundColor: '#fff', pointHoverBorderColor: '#48753aff' }] },
        options: { responsive: true, maintainAspectRatio: false, scales: { r: { angleLines: { display: true }, suggestedMin: 0, suggestedMax: 100, pointLabels: { font: { size: 12 } }, ticks: { display: false } } } }
    });
}


// ... (其他函式如 renderPageBasedOnUrl, showSection, parseCSVLine 等不變)
// 渲染食譜卡片
function renderRecipes() {
    if (!recipeGrid) return;
    if (recipes.length === 0) {
        recipeGrid.innerHTML = `<p>查無此蔬菜的食譜</p>`;
        return;
    }
    recipeGrid.innerHTML = recipes.map(recipe => `
        <div class="recipe-card" onclick="showRecipeDetail(${recipe.id}, true)" data-name="${recipe.title.toLowerCase()}">
            <img src="${recipe.imageUrl}" alt="${recipe.title}" loading="lazy">
            <div class="card-content">
                <h3>${recipe.title}</h3>
                <p>${recipe.instructions.substring(0, 80) + '...'}</p>
                <div class="recipe-meta">
                    <span><i class="fas fa-clock"></i> 30分鐘</span>
                    <span><i class="fas fa-signal"></i> 簡單</span>
                </div>
            </div>
        </div>`).join('');
}

// 讀取蔬菜標籤
async function fetchVegetableTags() {
    try {
        // 使用已載入的 allVegetables，避免重複呼叫 API
        vegetableTagsContainer.innerHTML = allVegetables.map(veg =>
            `<div class="vegetable-tag" data-id="${veg.id}">${veg.name}</div>`
        ).join('');

        document.querySelectorAll('.vegetable-tag').forEach(tag => {
            tag.addEventListener('click', async function () {
                document.querySelectorAll('.vegetable-tag').forEach(t => t.classList.remove('active'));
                this.classList.add('active');
                const vegId = this.getAttribute('data-id');
                await fetchRecipesByVegId(vegId);
            });
        });

    } catch (error) {
        console.error('載入蔬菜標籤失敗:', error);
    }
}

async function fetchRecipesByVegId(vegId) {
    try {
        const response = await fetch(`/api/recipes/${vegId}`);
        if (response.status === 404) {
            recipes = [];
            if (recipeGrid) recipeGrid.innerHTML = `<p>查無此蔬菜的食譜</p>`;
            return;
        }
        if (!response.ok) throw new Error('無法取得食譜列表');
        recipes = await response.json();
        renderRecipes();
    } catch (error) {
        console.error('載入食譜資料失敗:', error);
    }
}


// 顯示蔬菜詳細頁面
// 修改 showVegetableDetail 函式以使用後端 API
async function showVegetableDetail(id, pushState = true) {
    if (pushState) {
        history.pushState({ type: 'vegetable', id: id, section: 'detail' }, '', `/?section=detail&id=${id}`);
    }

    document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active'));
    navItems.forEach(n => n.classList.remove('active'));

    const mainContent = document.querySelector('.main-content');
    document.getElementById('detailPage')?.remove();

    let detailSection = document.createElement('section');
    detailSection.id = 'detailPage';
    detailSection.className = 'content-section active';
    detailSection.innerHTML = `
        <div class="loading-spinner">
            <i class="fas fa-spinner fa-spin"></i> 載入中...
        </div>
    `;
    mainContent.appendChild(detailSection);

    try {
        // 從後端 API 獲取蔬菜詳細資訊
        const vegResponse = await fetch(`/api/vegetables/${id}`); // 假設你新增了這個 API
        if (!vegResponse.ok) throw new Error('Failed to fetch vegetable data');
        const vegetable = await vegResponse.json();

        // 從後端 API 獲取相關食譜
        const recipeResponse = await fetch(`/api/recipes/${id}`);
        if (!recipeResponse.ok) throw new Error('Failed to fetch recipes');
        const relatedRecipes = await recipeResponse.json();

        // 檢查是否成功獲取資料
        if (!vegetable) {
            detailSection.innerHTML = `
                <div class="detail-container">
                    <p>找不到此蔬菜的詳細資訊。</p>
                    <button class="btn btn-primary" onclick="goBackToOverview()"><i class="fas fa-arrow-left"></i> 返回蔬菜總覽</button>
                </div>
            `;
            return;
        }

        // 動態生成 HTML (這部分維持不變)
        detailSection.innerHTML = `
            <div class="detail-container">
                <div class="back-button-container">
                    <button class="btn btn-primary" onclick="goBackToOverview()"><i class="fas fa-arrow-left"></i> 返回蔬菜總覽</button>
                </div>
                <header class="detail-header">
                    <img src="${vegetable.imageUrl}" alt="${vegetable.name}" class="detail-header-image">
                    <div class="detail-header-info">
                        <h1>${vegetable.name}</h1>
                        <p class="description">${vegetable.description || '無描述'}</p>
                        <div class="tags">
                            <span class="tag">${vegetable.season || '全年'}盛產</span>
                            <span class="tag price-change-tag ${vegetable.priceChange && vegetable.priceChange.includes('+') ? 'increase' : 'decrease'}">
                                ${vegetable.priceChange || 'N/A'}
                            </span>
                        </div>
                        <div class="current-price">目前價格：NT$ ${vegetable.currentPrice || 'N/A'} / 公斤</div>
                    </div>
                </header>
                
                <div class="charts-container">
                    <div class="chart-card">
                        <h3><i class="fas fa-chart-line"></i> 價格趨勢</h3>
                        <div class="time-select">
                           <button onclick="updatePriceChart(event, 'detail-priceChart', ${vegetable.id}, 7, this)">近7天</button>
                           <button onclick="updatePriceChart(event, 'detail-priceChart', ${vegetable.id}, 14, this)">近14天</button>
                           <button class="active" onclick="updatePriceChart(event, 'detail-priceChart', ${vegetable.id}, 30, this)">近30天</button>
                        </div>
                        <div class="chart-wrapper"><canvas id="detail-priceChart"></canvas></div>
                    </div>
                    <div class="chart-card">
                        <h3><i class="fas fa-chart-pie"></i> 營養佔比</h3>
                        <div class="chart-wrapper"><canvas id="detail-nutritionChart"></canvas></div>
                    </div>
                </div>

                <section class="detail-section">
                    <h3><i class="fas fa-balance-scale"></i> 營養價值 (每100g)</h3>
                    <div class="nutrition-grid">
                        ${Object.entries(vegetable.nutrition || {}).map(([key, val]) => `
                            <div class="nutrition-item">
                                <div class="value">${val}${getUnit(key)}</div>
                                <small>${key}</small>
                            </div>
                        `).join('')}
                    </div>
                </section>
                
                <section class="detail-section related-recipes">
                    <h3><i class="fas fa-utensils"></i> 相關食譜推薦</h3>
                    ${relatedRecipes && relatedRecipes.length > 0 ? `
                        <div class="recipes-grid">
                            ${relatedRecipes.slice(0, 5).map(recipe => `
                                <div class="recipe-card" onclick="window.location.href='/?section=recipe&id=${recipe.id}'">
                                    <img src="${recipe.imageUrl}" alt="${recipe.title}" loading="lazy">
                                    <div class="card-content">
                                        <h4>${recipe.title}</h4>
                                        <p><strong>食譜說明：</strong>${recipe.instructions.split('\\n')[0]}...</p>
                                    </div>
                                </div>`).join('')}
                        </div>` :
                `<p>暫無相關食譜</p>`}                  
                </section>
            </div>
        `;

        // === 修改開始：只篩選指定的營養素給雷達圖 ===
        setTimeout(() => {
            updatePriceChart(null, `detail-priceChart`, vegetable.id, 30);
            const nutritionCanvas = document.getElementById(`detail-nutritionChart`);

            // 檢查畫布和營養數據是否存在
            if (nutritionCanvas && vegetable.nutrition) {
                const fullNutrition = vegetable.nutrition; // 完整的營養數據

                // 1. 定義雷達圖要顯示的營養素
                const radarChartKeys = ['水', '蛋白質', '脂肪', '碳水化合物', '膳食纖維', '糖'];

                const chartLabels = [];
                const chartDataValues = [];

                // 2. 從完整數據中，篩選出雷達圖需要的資料
                radarChartKeys.forEach(key => {
                    // 檢查蔬菜是否包含這項營養素
                    if (fullNutrition.hasOwnProperty(key)) {
                        chartLabels.push(key);
                        chartDataValues.push(fullNutrition[key]);
                    }
                });

                // 3. 為了讓雷達圖比例好看，設定一個參考最大值
                // (這些值可以根據常見蔬菜的營養分佈進行微調)
                const maxValues = {
                    '水': 100,          // 100g中最多100g是水
                    '蛋白質': 7,         // 一般蔬菜蛋白質含量不高
                    '脂肪': 0.5,            // 一般蔬菜脂肪含量很低
                    '碳水化合物': 30,
                    '膳食纖維': 10,
                    '糖': 7
                };

                // 4. 將原始數值轉換為百分比 (0-100)，以便在同一個圖表上比較
                const normalizedData = chartDataValues.map((value, index) => {
                    const key = chartLabels[index];
                    const max = maxValues[key] || 100; // 如果沒有設定最大值，預設為100
                    // 確保百分比在 0 到 100 之間
                    return Math.min(100, Math.max(0, (value / max) * 100));
                });

                // 5. 使用篩選和標準化後的資料來渲染雷達圖
                renderRadarChart(nutritionCanvas, chartLabels, normalizedData, '主要營養素佔比(%)');
            }
        }, 100);
        // === 修改結束 ===

        if (window.innerWidth <= 768) sidebar.classList.remove('active');
        window.scrollTo(0, 0);

    } catch (error) {
        console.error('Error fetching vegetable details:', error);
        detailSection.innerHTML = `
            <div class="detail-container">
                <p>載入詳細資訊時發生錯誤。請稍後再試。</p>
                <button class="btn btn-primary" onclick="goBackToOverview()"><i class="fas fa-arrow-left"></i> 返回蔬菜總覽</button>
            </div>
        `;
    }
}

// 輔助函式，根據營養成分名稱回傳單位
function getUnit(key) {
    if (key.includes('熱量')) return '卡';
    if (key.includes('g') || key.includes('克') || key.includes('蛋白質') || key.includes('纖維')) return 'g';
    if (key.includes('微克')) return 'μg';
    return 'mg';
}

// 注意：這段程式碼依賴於後端新增一個 `/api/vegetables/<int:id>` 的 API 端點，
// 該端點應回傳單一蔬菜的所有詳細資訊，包括價格、季節和營養資料。
// 如果沒有這個 API，前端將無法取得資料。

// 顯示食譜詳細頁面
function showRecipeDetail(id, pushState = true) {
    const recipe = recipes.find(r => r.id == id);
    if (!recipe) return;

    if (pushState) {
        history.pushState({ type: 'recipe', id: id }, '', `/?section=recipe&id=${id}`);
    }

    document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active'));
    document.getElementById('detailPage')?.remove();

    let detailSection = document.createElement('section');
    detailSection.id = 'detailPage';
    detailSection.className = 'content-section active';
    document.querySelector('.main-content').appendChild(detailSection);

    detailSection.innerHTML = `
        <div class="detail-container">
            <div class="back-button-container">
                <button class="btn btn-primary" onclick="goBackToRecipes()"><i class="fas fa-arrow-left"></i> 返回食譜列表</button>
            </div>
            <header class="detail-header recipe-header">
                <img src="${recipe.imageUrl}" alt="${recipe.title}" class="detail-header-image">
                <div class="detail-header-info">
                    <h1>${recipe.title}</h1>
                    <div class="recipe-header-meta">
                        <div class="meta-item"><i class="fas fa-clock"></i><span>30分鐘</span></div>
                        <div class="meta-item"><i class="fas fa-signal"></i><span>簡單</span></div>
                        <div class="meta-item"><i class="fas fa-users"></i><span>2-3人份</span></div>
                    </div>
                </div>
            </header>

            <section class="detail-section">
                <h3><i class="fas fa-shoe-prints"></i> 烹飪步驟</h3>
                <div class="steps-container">
                    <div class="step-item">
                        <div class="step-content">
                            <p class="description">${recipe.instructions.replace(/\n/g, '<br>')}</p>
                        </div>
                    </div>
                </div>
            </section>
        </div>`;

    if (window.innerWidth <= 768) sidebar.classList.remove('active');
    window.scrollTo(0, 0);
}

function showSingleRecipeDetail(recipe) {
    document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active'));
    document.getElementById('detailPage')?.remove();

    let detailSection = document.createElement('section');
    detailSection.id = 'detailPage';
    detailSection.className = 'content-section active';
    document.querySelector('.main-content').appendChild(detailSection);

    detailSection.innerHTML = `
        <div class="detail-container">
            <div class="back-button-container">
                <button class="btn btn-primary" onclick="goBackToRecipes()"><i class="fas fa-arrow-left"></i> 返回食譜列表</button>
            </div>
            <header class="detail-header recipe-header">
                <img src="${recipe.imageUrl}" alt="${recipe.title}" class="detail-header-image">
                <div class="detail-header-info">
                    <h1>${recipe.title}</h1>
                    <div class="recipe-header-meta">
                        <div class="meta-item"><i class="fas fa-clock"></i><span>30分鐘</span></div>
                        <div class="meta-item"><i class="fas fa-signal"></i><span>簡單</span></div>
                        <div class="meta-item"><i class="fas fa-users"></i><span>2-3人份</span></div>
                    </div>
                </div>
            </header>

            <section class="detail-section">
                <h3><i class="fas fa-shoe-prints"></i> 烹飪步驟</h3>
                <div class="steps-container">
                    <div class="step-item">
                        <div class="step-content">
                            <p class="description">${recipe.instructions.replace(/\n/g, '<br>')}</p>
                        </div>
                    </div>
                </div>
            </section>
        </div>`;

    if (window.innerWidth <= 768) sidebar.classList.remove('active');
    window.scrollTo(0, 0);
}


// 返回函式
function goBackToOverview() {
    const currentSeason = document.querySelector('.season-filter-btn.active')?.dataset.season || 'all';
    let newUrl = '/?section=overview';
    if (currentSeason !== 'all') {
        newUrl += `&season=${currentSeason}`;
    }
    history.pushState({ page: 'overview' }, '', newUrl);

    // 新增：移除可能殘留的詳細頁面元素
    document.getElementById('detailPage')?.remove();

    showSection('overview', false);
}

function goBackToRecipes() {
    const recipeSection = document.getElementById('recipe');
    if (recipeSection) {
        document.getElementById('detailPage')?.remove();
        showSection('recipe');
    }
}

function handleChatInput() {
    const message = chatInput.value.trim();
    if (message) {
        appendMessage('user', message);
        chatInput.value = '';
    }
}

function appendMessage(sender, message) {
    const messageElement = document.createElement('div');
    messageElement.classList.add('chat-message', sender);
    messageElement.innerHTML = `<p>${message}</p>`;
    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}


// 統一設置所有事件監聽器
function setupEventListeners() {
    if (menuToggle) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.toggle('active');
        });
    }

    navItems.forEach(item => {
        item.addEventListener('click', function (event) {
            event.preventDefault();
            const targetId = this.getAttribute('data-section');
            if (targetId) {
                showSection(targetId);
            }
        });
    });

    if (seasonFilterContainer) {
        seasonFilterContainer.addEventListener('click', (event) => {
            if (event.target.classList.contains('season-filter-btn')) {
                const selectedSeason = event.target.dataset.season;

                updateSeasonFilterButtons(selectedSeason);

                // 使用新季節篩選並更新全域 `vegetables` 變數
                vegetables = filterBySeason(allVegetables, selectedSeason);

                // 使用篩選後的資料重新渲染
                renderVegetables();
                renderPricePredictions();

                // 更新 URL 以反映當前篩選狀態
                let newUrl = `/?section=overview`;
                if (selectedSeason !== 'all') {
                    newUrl += `&season=${selectedSeason}`;
                }
                history.pushState({ section: 'overview', season: selectedSeason }, '', newUrl);
            }
        });
    }


    if (chatToggle) {
        chatToggle.addEventListener('click', () => {
            chatBody.classList.toggle('active');
            if (chatBody.classList.contains('active')) {
                chatInput.focus();
            }
        });
    }

    if (sendMessage) {
        sendMessage.addEventListener('click', () => {
            handleChatInput();
        });
    }

    if (chatInput) {
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                handleChatInput();
            }
        });
    }

    const recipeSearch = document.getElementById('recipeSearch');
    if (recipeSearch) {
        recipeSearch.addEventListener('input', e => {
            const term = e.target.value.toLowerCase();
            document.querySelectorAll('#recipeGrid .recipe-card').forEach(card => {
                const nameMatch = card.dataset.name.includes(term);
                card.style.display = nameMatch ? 'flex' : 'none';
            });
        });
    }

    window.addEventListener('popstate', (event) => {
        if (event.state) {
            if (event.state.type === 'recipe') {
                showRecipeDetail(event.state.id, false);
            } else {
                showSection(event.state.target, false);
            }
        }
    });

    // 處理圖片上傳按鈕的點擊事件
    if (uploadBtn) {
        uploadBtn.addEventListener('click', () => {
            imageUpload.click(); // 模擬點擊文件選擇框
        });
    }
    // 處理圖片上傳的change事件
    if (imageUpload) {
        imageUpload.addEventListener('change', handleImageUpload);
    }
}



// 修改後的圖片上傳處理函式
async function handleImageUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    // 1. 立即在前端顯示圖片預覽
    const imageUrl = URL.createObjectURL(file);
    const imageHtml = `<img src="${imageUrl}" alt="上傳的圖片" style="max-width: 200px;">`;
    addMessage(imageHtml, 'user');

    // 清空 input 的值，以便能重複上傳同一張照片
    event.target.value = '';

    // 2. 顯示 "分析中" 的訊息，提升使用者體驗
    addMessage('圖片分析中，請稍候...', 'bot');

    // 3. 將圖片檔案轉換為 Base64 字串
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = async () => {
        const base64String = reader.result;

        // 4. 使用 fetch API 將 Base64 字串發送到 Flask 後端
        try {
            // 確認後端 API 的 URL 和 port 是否正確
            const response = await fetch(`${url_5000}/predict`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ image: base64String }),
            });

            if (!response.ok) {
                // 如果伺服器回傳錯誤 (例如 400 或 500)
                throw new Error(`伺服器錯誤: ${response.status}`);
            }

            const result = await response.json();

            if (result.vegetable && result.confidence !== undefined) {
                const veg_name = result.vegetable;
                // 後端回傳的 confidence 是 0-100
                const confidence = parseFloat(result.confidence);
                let reply = '';

                if (confidence === 100) {
                    reply = `真相只有一個 就是「${veg_name}」!! (信心度: ${confidence.toFixed(2)}%)`;
                } else if (confidence >= 80) {
                    reply = `哼哼 根據我的判斷 它就是「${veg_name}」! (信心度: ${confidence.toFixed(2)}%)`;
                } else if (confidence >= 50) { // 假設原始需求 ">= 0.5" 是指 50%
                    reply = `可能是「${veg_name}」，也許讓我再看更清楚的一張。 (信心度: ${confidence.toFixed(2)}%)`;
                } else { // 信心度 < 50%
                    reply = `歐內該，請提供更清晰的照片。 (信心度: ${confidence.toFixed(2)}%)`;
                }
                addMessage(reply, 'bot');

            } else {
                // 如果後端回傳的 JSON 中有 error 欄位或格式不符
                throw new Error(result.error || '未知的辨識結果');
            }

        } catch (error) {
            console.error('辨識失敗:', error);
            addMessage('抱歉，圖片辨識失敗，請稍後再試。', 'bot');
        }
    };
    reader.onerror = (error) => {
        console.error('檔案讀取失敗:', error);
        addMessage('抱歉，讀取圖片檔案時發生錯誤。', 'bot');
    };
}


// 聊天功能
function sendChatMessage() {
    const message = chatInput.value.trim();
    if (!message) return;
    addMessage(message, 'user');
    chatInput.value = '';
    setTimeout(() => addMessage(generateAIResponse(message), 'bot'), 1000);
}
function addMessage(text, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    messageDiv.innerHTML = `<i class="fas ${sender === 'bot' ? 'fa-robot' : 'fa-user'}"></i><span>${text}</span>`;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}
function generateAIResponse(message) {
    const responses = { '大白菜': '大白菜是十字花科蔬菜，富含維生素C和纖維，適合炒、煮、滷等多種烹調方式。', '營養': '想查詢哪種蔬菜的營養呢？例如：番茄營養。', '食譜': '請告訴我您想用什麼食材來找食譜？', '價格': '蔬菜價格會受季節、天氣和市場供需影響，您可以參考我們的價格預測頁面。' };
    for (let key in responses) { if (message.includes(key)) return responses[key]; }
    return '感謝您的提問，我會持續學習以提供更好的幫助。您可以試著問我「空心菜食譜」或「黃瓜價格」。';
}