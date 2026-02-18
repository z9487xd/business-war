let playerId = localStorage.getItem("io_player_id");
let itemsMeta = {};

let lastSeenEventId = null;
let isNewsOpen = false;
let tradeMode = "MARKET";

// 用於即時計算庫存檢查的變數
let currentPlayerInventory = {};

if (playerId) {
    document.getElementById("login-section").classList.add("hidden");
    document.getElementById("game-ui").classList.remove("hidden");
    startPolling();
}

// --- 浮動提示 ---
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = message;
    container.appendChild(toast);
    requestAnimationFrame(() => { toast.classList.add('show'); });
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function setTradeMode(mode) {
    tradeMode = mode;
    const btnM = document.getElementById("mode-market");
    const btnG = document.getElementById("mode-gov");
    const typeSel = document.getElementById("trade-type");
    
    if (mode === "MARKET") {
        btnM.style.opacity = 1; btnG.style.opacity = 0.5;
        typeSel.innerHTML = `<option value="BID">買入 (BID) - 花錢買貨</option><option value="ASK">賣出 (ASK) - 賣貨換錢</option>`;
        typeSel.disabled = false;
    } else {
        btnM.style.opacity = 0.5; btnG.style.opacity = 1;
        typeSel.innerHTML = `<option value="GOV_ASK">🏛️ 賣給政府 (投標)</option>`;
        typeSel.disabled = true; 
    }
}

function closeNewsModal() {
    isNewsOpen = false;
    document.getElementById("news-modal-overlay").classList.add("hidden");
}

async function register() {
    const name = document.getElementById("player-name").value;
    if (!name) return showToast("請輸入公司名稱！", "error");
    try {
        const res = await fetch("/api/register", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name}) });
        const data = await res.json();
        playerId = data.player_id;
        localStorage.setItem("io_player_id", playerId);
        showToast("公司註冊成功！", "success");
        // 直接切換顯示，無需刷新
        document.getElementById("login-section").classList.add("hidden");
        document.getElementById("game-ui").classList.remove("hidden");
        startPolling(); 
    } catch (e) { showToast("無法連接伺服器", "error"); }
}

function startPolling() { setInterval(fetchState, 1000); }

async function fetchState() {
    try {
        const url = playerId ? `/api/state?player_id=${playerId}` : '/api/state';
        const res = await fetch(url);
        const state = await res.json();
        itemsMeta = state.items_meta;

        if (playerId && !state.player) {
            showToast("⚠️ 遊戲已重置，請重新創立公司！", "error");
            localStorage.removeItem("io_player_id");
            setTimeout(() => location.reload(), 2000);
            return;
        }

        updateUI(state);
    } catch (e) {
        console.error("Polling error", e);
    }
}

function updateUI(state) {
    const phase = state.phase;
    const event = state.event || { id: "none", title: "等待訊號...", description: "", effect_text: "" };
    const govEvent = state.gov_event; 

    // 1. 新聞顯示邏輯
    const modal = document.getElementById("news-modal-overlay");
    const ticker = document.getElementById("news-ticker-bar");

    if (phase === 1) {
        if (event.id !== lastSeenEventId) {
            lastSeenEventId = event.id;
            isNewsOpen = true;
        }
        if (isNewsOpen) modal.classList.remove("hidden");
        else modal.classList.add("hidden");

        ticker.classList.add("hidden");
        document.getElementById("modal-title").innerText = event.title;
        document.getElementById("modal-desc").innerText = event.description;
        document.getElementById("modal-effect").innerText = event.effect_text;
    } else {
        modal.classList.add("hidden");
        ticker.classList.remove("hidden");
        
        let tickerText = `【${event.title}】 ${event.effect_text}`;
        if (govEvent) {
            const targetsDisplay = govEvent.targets.map(t => itemsMeta[t]?.label || t).join("、");
            tickerText += `      ///    政府採購：${govEvent.title}】 目標：${targetsDisplay} (售價 +50%)`;
        }
        document.getElementById("ticker-text").innerText = tickerText + "      ///      " + tickerText;
    }

    // 2. 狀態列更新
    const phaseNames = {1: "新聞階段", 2: "行動階段", 3: "交易階段", 4: "結算階段"};
    const turnText = state.turn ? `(第 ${state.turn} 回合)` : "";
    document.getElementById("phase-display").innerText = `${phase}. ${phaseNames[phase] || "未知"} ${turnText}`;
    
    document.getElementById("action-panel").classList.toggle("hidden", phase !== 2);
    document.getElementById("trading-panel").classList.toggle("hidden", phase !== 3);

    if (state.player) {
        currentPlayerInventory = state.player.inventory; // 更新全域庫存
        
        document.getElementById("money-display").innerText = `$${state.player.money.toLocaleString()}`;
        document.getElementById("land-display").innerText = `土地: ${state.player.factories.length}/${state.player.land_limit}`;
        
        // 庫存列表 (這裡可以用innerHTML，因為它是純展示，不會有點擊操作中斷的問題)
        const invDiv = document.getElementById("inventory-list");
        const invHtml = Object.entries(state.player.inventory)
            .filter(([_, v]) => v > 0)
            .map(([k, v]) => `<div class="row"><span>${itemsMeta[k]?.label || k}</span> <span class="tag">x${v}</span></div>`)
            .join("");
        invDiv.innerHTML = invHtml || `<div style="color: #555; font-style: italic;">(倉庫是空的)</div>`;

        // 3. 工廠渲染 (使用智慧更新)
        renderFactoriesSmart(state.player.factories, state.phase);
        populatePaymentDropdowns(state.player.inventory);
    }
    
    populateDropdown("trade-item", state.items_meta, state.market_prices, 1.0);
    populateDropdown("bank-item", state.items_meta, state.market_prices, 0.85);
}

// --- 核心：智慧更新工廠列表 ---
// 解決選單跳掉、刷新閃爍的問題
function renderFactoriesSmart(factories, phase) {
    const list = document.getElementById("factory-list");
    
    // 1. 如果工廠數量變了(建造/拆除)，或者列表是空的，則進行全量重繪 (Full Redraw)
    // 這是唯一會打斷選單的情況，但建造/拆除後本來就該重整
    if (list.children.length !== factories.length) {
        list.innerHTML = ""; // 清空
        factories.forEach(f => {
            const div = document.createElement("div");
            div.className = "factory-box";
            div.id = `factory-box-${f.id}`; // 賦予 ID 以便後續追蹤
            div.innerHTML = generateFactoryInnerHtml(f, phase);
            list.appendChild(div);
            
            // 初始化配方檢查 (如果有選單)
            if(document.getElementById(`prod-${f.id}`)) {
                checkRecipe(f.id);
            }
        });
        return;
    }

    // 2. 如果數量沒變，進行「原地更新 (In-Place Update)」
    factories.forEach((f, index) => {
        const div = document.getElementById(`factory-box-${f.id}`);
        // 防呆：如果找不到對應的 DOM，就略過 (照理說長度檢查已擋掉)
        if (!div) return; 

        // A. 更新標題 (Tier 顏色可能變)
        const titleRow = div.querySelector(".row");
        const displayName = f.name.replace("Miner", "採集器").replace("Factory", "加工廠");
        titleRow.innerHTML = `
            <strong style="color: #fff;">${displayName}</strong>
            <span class="tag" style="background: ${f.tier===0?'#555':(f.tier===1?'#3498db':(f.tier===2?'#9b59b6':'#e67e22'))}">Lv.${f.tier}</span>
        `;

        // B. 更新操作區 (Action Area)
        // 這裡我們不替換整個 HTML，而是針對按鈕做狀態更新
        // *重點*：絕對不要動 `<select>`，除非它是新生成的
        
        // 檢查是否處於 Phase 2
        if (phase === 2) {
            const isMiner = f.name.includes("Miner");
            
            if (isMiner) {
                // 採集器邏輯
                const btn = div.querySelector("button.btn-green");
                const select = div.querySelector("select");
                
                if (f.has_produced) {
                    // 如果已開採，隱藏選單與按鈕，顯示文字
                    if(btn) btn.parentElement.innerHTML = `<span style="color: #aaa;">✅ 本回合已開採</span>`;
                } else {
                    // 如果還沒開採，但畫面顯示已開採 (回合重置)，則需要重建按鈕
                    // 或是 DOM 結構不對，就重繪這一個工廠
                    if (!btn && !select) {
                        div.innerHTML = generateFactoryInnerHtml(f, phase);
                    }
                }
            } else {
                // 加工廠邏輯
                // 我們只觸發 checkRecipe 來更新紅綠燈，不動 input/select 的值
                checkRecipe(f.id);
            }
        } else {
            // 非行動階段
            const currentContent = div.innerHTML;
            if (!currentContent.includes("等待行動階段")) {
                div.innerHTML = generateFactoryInnerHtml(f, phase);
            }
        }
    });
}

// 產生單個工廠內部的 HTML 字串
function generateFactoryInnerHtml(f, phase) {
    let actionHtml = "";
    const isMiner = f.name.includes("Miner");
    
    // 計算拆除費用
    let demolishCost = 0;
    if (isMiner) demolishCost = 250; 
    else {
        if (f.tier === 1) demolishCost = 500;
        else if (f.tier === 2) demolishCost = 1000;
        else if (f.tier === 3) demolishCost = 4000;
    }

    if (phase === 2) {
        if (isMiner) {
            if (f.has_produced) {
                actionHtml = `<span style="color: #aaa;">✅ 本回合已開採</span>`;
            } else {
                let options = "";
                for (const [code, meta] of Object.entries(itemsMeta)) {
                    if (meta.tier === 0) options += `<option value="${code}">${meta.label}</option>`;
                }
                actionHtml = `
                    <div class="row" style="gap:5px;">
                        <select id="prod-${f.id}" style="flex:2;">${options}</select>
                        <button class="btn btn-green" style="flex:1; margin:0;" onclick="produce('${f.id}')">開採</button>
                    </div>`;
            }
        } else {
            // 加工廠
            let options = "";
            for (const [code, meta] of Object.entries(itemsMeta)) {
                if (meta.tier > 0 && meta.tier <= f.tier) options += `<option value="${code}">${meta.label}</option>`;
            }
            if (options) {
                actionHtml = `
                    <div class="row" style="gap:5px; margin-bottom: 5px;">
                        <select id="prod-${f.id}" style="flex:2;" onchange="checkRecipe('${f.id}')">${options}</select>
                        <input type="number" id="qty-${f.id}" value="1" min="1" style="flex:1; padding:8px;" placeholder="量" oninput="checkRecipe('${f.id}')">
                        <button class="btn btn-green" style="flex:1; margin:0;" onclick="produce('${f.id}')">生產</button>
                    </div>
                    <div id="recipe-${f.id}" class="recipe-display"></div>
                `;
            } else actionHtml = "<span style='color:#aaa;'>無可生產配方</span>";
        }

        // 升級按鈕
        if (f.tier < 3) {
                let req = "";
                if (isMiner) req = "需: 材料A (3個 T1產品)"; 
                else if (f.tier === 1) req = "需: 材料A+B (各5個 T1產品)"; 
                else req = "需: 材料A+B (各3個 T2) + C (10個 T1)"; 
                actionHtml += `<button class="btn btn-orange" style="padding:6px; font-size:0.9em; margin-top:8px;" onclick="upgrade('${f.id}')">升級工廠 (${req})</button>`;
        }
        
        // 拆除按鈕
        actionHtml += `
            <button class="btn btn-red" style="padding:6px; font-size:0.9em; margin-top:8px;" onclick="demolish('${f.id}', ${demolishCost})">
                拆除設施 (花費 $${demolishCost})
            </button>
        `;
    } else {
        actionHtml = `<span style="color: #666; font-size: 0.9em;">等待行動階段...</span>`;
    }

    let displayName = f.name.replace("Miner", "採集器").replace("Factory", "加工廠");
    return `
        <div class="row">
            <strong style="color: #fff;">${displayName}</strong>
            <span class="tag" style="background: ${f.tier===0?'#555':(f.tier===1?'#3498db':(f.tier===2?'#9b59b6':'#e67e22'))}">Lv.${f.tier}</span>
        </div>
        ${actionHtml}
    `;
}

// --- 配方檢查功能 ---
function checkRecipe(factoryId) {
    const select = document.getElementById(`prod-${factoryId}`);
    const qtyInput = document.getElementById(`qty-${factoryId}`);
    const displayDiv = document.getElementById(`recipe-${factoryId}`);
    
    // 如果找不到元件 (可能因為是 Miner 或是 Phase 不對)，就跳過
    if(!select || !qtyInput || !displayDiv) return;

    const targetItem = select.value;
    // 如果下拉選單是空的 (例如無配方)，則返回
    if (!targetItem) {
        displayDiv.innerHTML = "";
        return;
    }

    const quantity = parseInt(qtyInput.value) || 1;
    const itemData = itemsMeta[targetItem];

    if (!itemData || !itemData.recipe) {
        displayDiv.innerHTML = "";
        return;
    }

    let html = `<div>🛠️ <strong>配方需求 (生產 x${quantity}):</strong></div>`;
    
    for (const [ingId, reqQty] of Object.entries(itemData.recipe)) {
        const totalReq = reqQty * quantity;
        const have = currentPlayerInventory[ingId] || 0;
        const meta = itemsMeta[ingId];
        
        const statusClass = have >= totalReq ? "recipe-ok" : "recipe-fail";
        const checkMark = have >= totalReq ? "✔" : "✘";
        
        html += `
            <span class="recipe-item ${statusClass}">
                ${meta.label}: ${totalReq} (庫存: ${have}) ${checkMark}
            </span>
        `;
    }
    displayDiv.innerHTML = html;
}

function populateDropdown(elementId, meta, prices, priceRatio) {
    if (document.activeElement && document.activeElement.id === elementId) return;
    const sel = document.getElementById(elementId);
    if (!sel) return; // 防呆

    const currentVal = sel.value;
    let html = "";
    for (const [k, v] of Object.entries(meta)) {
        const marketP = (prices && prices[k] !== undefined) ? prices[k] : v.base_price;
        const finalP = Math.floor(marketP * priceRatio);
        html += `<option value="${k}">${v.label} ($${finalP})</option>`;
    }
    // 只有當內容有變時才更新，避免選單重繪
    if (sel.innerHTML !== html) {
        sel.innerHTML = html;
        if(currentVal) sel.value = currentVal;
    }
}

function populatePaymentDropdowns(inventory) {
    // 如果使用者正在操作其中一個下拉選單，就完全不要更新，避免干擾
    if (document.activeElement && document.activeElement.tagName === "SELECT" && document.activeElement.id.startsWith("pay-mat")) return;
    
    let options = `<option value="">無 (None)</option>`;
    for (const [k, v] of Object.entries(inventory)) {
        if (v > 0) options += `<option value="${k}">${itemsMeta[k].label} (庫存: ${v})</option>`;
    }
    ['pay-mat-1', 'pay-mat-2', 'pay-mat-3'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
             const val = el.value; 
             // 簡單比對長度來決定是否更新，減少 DOM 操作
             if (el.innerHTML.length !== options.length) {
                 el.innerHTML = options; 
                 el.value = val; // 嘗試還原選值
             }
        }
    });
}

function getPayment() {
    const m1 = document.getElementById("pay-mat-1").value;
    const m2 = document.getElementById("pay-mat-2").value;
    const m3 = document.getElementById("pay-mat-3").value;
    const list = [];
    if(m1) list.push(m1);
    if(m2) list.push(m2);
    if(m3) list.push(m3);
    return list;
}

async function produce(factoryId) {
    const item = document.getElementById(`prod-${factoryId}`).value;
    const qtyInput = document.getElementById(`qty-${factoryId}`);
    const qty = qtyInput ? (parseInt(qtyInput.value) || 1) : 1;
    await post("/api/produce", {player_id: playerId, factory_id: factoryId, target_item: item, quantity: qty});
}
async function buildMiner() { await post("/api/build", {player_id: playerId, target_tier: 0, payment_materials: []}); }
async function buildFactory() {
    const pay = getPayment();
    if(pay.length < 2) return showToast("請在「選擇付款材料」中選擇 材料A 與 材料B！", "error");
    await post("/api/build", {player_id: playerId, target_tier: 1, payment_materials: pay}); 
}
async function upgrade(fid) { 
    const pay = getPayment();
    await post("/api/upgrade", {player_id: playerId, factory_id: fid, payment_materials: pay}); 
}
async function demolish(fid, cost) {
    if(!confirm(`確定要拆除這座設施嗎？\n這將花費 $${cost} 的清潔費，且設施將永久消失！`)) return;
    await post("/api/demolish", {player_id: playerId, factory_id: fid});
}
async function sellToBank() {
    const item = document.getElementById("bank-item").value;
    const qty = parseInt(document.getElementById("bank-qty").value);
    if(!qty) return showToast("請輸入數量", "error");
    await post("/api/bank_sell", {player_id: playerId, item_id: item, quantity: qty});
}
async function submitOrder() {
    const price = parseInt(document.getElementById("trade-price").value);
    const qty = parseInt(document.getElementById("trade-qty").value);
    if(!price || !qty) return showToast("請輸入有效的價格與數量", "error");
    await post("/api/trade", {
        player_id: playerId,
        type: document.getElementById("trade-type").value,
        item_id: document.getElementById("trade-item").value,
        price: price,
        quantity: qty
    });
}

// 統一的 API 請求處理
async function post(url, data) {
    try {
        const res = await fetch(url, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data) });
        const json = await res.json();
        if (res.status !== 200) {
            showToast("錯誤: " + (json.detail || "未知錯誤"), "error");
        } else {
            if (json.message) showToast("成功: " + json.message, "success");
            // 成功後立即手動觸發一次狀態更新，讓畫面馬上反應
            fetchState();
        }
    } catch (e) {
        showToast("連接失敗", "error");
    }
}