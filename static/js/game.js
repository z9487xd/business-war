let playerId = localStorage.getItem("io_player_id");
let itemsMeta = {};
let lastSeenEventId = null;
let isNewsOpen = false;
let tradeMode = "MARKET";
let currentPlayerInventory = {};
let currentPlayerState = null; 
let currentMarketPrices = {}; 

let pendingAction = null;
let pendingTargetId = null; 
let selectedMaterials = [];

if (playerId) {
    document.getElementById("login-section").classList.add("hidden");
    document.getElementById("game-ui").classList.remove("hidden");
    startPolling();
}

window.alert = function(message, title = "系統宣告") {
    const alertModal = document.getElementById("sys-alert-modal");
    if (alertModal) {
        document.getElementById("sys-alert-title").innerText = title;
        document.getElementById("sys-alert-msg").innerText = message;
        alertModal.classList.remove("hidden");
    } else {
        console.log(title + ": " + message); 
    }
};

function showConfirm(message, title, onConfirmCallback) {
    const confirmModal = document.getElementById("sys-confirm-modal");
    if (!confirmModal) {
        if (window.confirm(message)) onConfirmCallback();
        return;
    }
    document.getElementById("sys-confirm-title").innerText = title;
    document.getElementById("sys-confirm-msg").innerText = message;
    
    const confirmBtn = document.getElementById("sys-confirm-yes");
    const newConfirmBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
    
    newConfirmBtn.onclick = function() {
        closeConfirmModal();
        onConfirmCallback();
    };
    
    document.getElementById("sys-confirm-no").onclick = closeConfirmModal;
    confirmModal.classList.remove("hidden");
}

function closeConfirmModal() {
    const confirmModal = document.getElementById("sys-confirm-modal");
    if (confirmModal) confirmModal.classList.add("hidden");
}

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

function closeNewsModal() {
    isNewsOpen = false;
    document.getElementById("news-modal-overlay").classList.add("hidden");
}

// ==========================================
// 1. 政府收購面板邏輯
// ==========================================
function setTradeMode(mode) {
    tradeMode = mode;
    const btnM = document.getElementById("mode-market");
    const btnG = document.getElementById("mode-gov");
    
    if (mode === "MARKET") {
        btnM.style.opacity = 1; btnG.style.opacity = 0.5;
        document.getElementById("ui-market").classList.remove("hidden");
        document.getElementById("ui-gov").classList.add("hidden");
    } else {
        btnM.style.opacity = 0.5; btnG.style.opacity = 1;
        document.getElementById("ui-market").classList.add("hidden");
        document.getElementById("ui-gov").classList.remove("hidden");
    }
}

// ==========================================
// 2. 倉庫智能驗證邏輯 (支援特殊設施系別判斷)
// ==========================================
function checkMaterialValidity(itemId, playerQty, action, targetId) {
    const meta = itemsMeta[itemId];
    if (!meta) return {valid: false, reason: "未知物品"};

    if (action === 'buildFactory') {
        if (meta.tier !== 0) return {valid: false, reason: "必須是 T0 原料"};
        if (playerQty < 3) return {valid: false, reason: "數量不足 (需 3 個)"};
        return {valid: true};
    }
    
    if (action === 'upgrade') {
        const f = currentPlayerState.factories.find(x => x.id === targetId);
        if (!f) return {valid: false, reason: "找不到該設施"};
        
        if (f.name.includes("Miner")) {
            if (f.tier === 0) {
                if (meta.tier !== 1) return {valid: false, reason: "需 T1 物品"};
                if (playerQty < 3) return {valid: false, reason: "數量不足 3 個"};
                return {valid: true};
            } else if (f.tier === 1) {
                if (meta.tier !== 2) return {valid: false, reason: "需 T2 物品"};
                if (playerQty < 3) return {valid: false, reason: "數量不足 3 個"};
                return {valid: true};
            } else if (f.tier === 2) {
                if (meta.tier !== 1 && meta.tier !== 2) return {valid: false, reason: "需 T1 或 T2 物品"};
                if (meta.tier === 1 && playerQty < 3) return {valid: false, reason: "T1 需 3 個"};
                if (meta.tier === 2 && playerQty < 3) return {valid: false, reason: "T2 需 3 個"};
                return {valid: true};
            }
        } else {
            if (f.tier === 1) {
                if (meta.tier !== 1) return {valid: false, reason: "必須是 T1 產品"};
                if (playerQty < 5) return {valid: false, reason: "數量不足 5 個"};
                return {valid: true};
            } else if (f.tier === 2) {
                if (meta.tier !== 1 && meta.tier !== 2) return {valid: false, reason: "必須是 T1 或 T2 產品"};
                if (meta.tier === 1 && playerQty < 10) return {valid: false, reason: "T1 需 10 個"};
                if (meta.tier === 2 && playerQty < 3) return {valid: false, reason: "T2 需 3 個"};
                return {valid: true};
            }
        }
    }
    
    // 特殊建築驗證邏輯
    if (action.startsWith('special_')) {
        if (action.includes('land') && meta.tier !== 3) return {valid: false, reason: "需 T3 物品"};
        
        if (action.includes('diamond')) {
            if (meta.tier !== 2) return {valid: false, reason: "需 T2 物品"};
            if (meta.series && meta.series === 'energy') return {valid: false, reason: "不需要能源系"};
        }
        
        if (action.includes('defense') || action.includes('accelerator')) {
            if (meta.tier !== 3) return {valid: false, reason: "需 T3 物品"};
            if (meta.series && meta.series === 'silicon') return {valid: false, reason: "不需要矽晶系"};
        }
        
        if (action.includes('omni')) {
            if (meta.tier !== 3) return {valid: false, reason: "需 T3 物品"};
            if (meta.series && meta.series !== 'energy') return {valid: false, reason: "萬能工廠只需能源系"};
        }
        
        if (action.includes('prophet')) return {valid: false, reason: "預言家功能已關閉"};
        
        return {valid: true};
    }
    return {valid: true};
}

function openWarehouseModal(actionType, targetId = null) {
    if (actionType === 'buildMiner') {
        post("/api/build", {player_id: playerId, target_tier: 0, payment_materials: []});
        return;
    }

    pendingAction = actionType;
    pendingTargetId = targetId;
    selectedMaterials = [];
    document.getElementById("confirm-warehouse-btn").disabled = true;
    
    const grid = document.getElementById("warehouse-selection-grid");
    grid.innerHTML = ""; 

    // 🌟 動態加入操作提示文字，讓玩家知道特殊建築要選什麼
    let helpText = "請選擇你要使用的材料：";
    if (actionType === 'special_land') helpText = "擴充土地：需 3 種【不同】的 T3 物品 (各扣 1 個)";
    else if (actionType === 'special_diamond') helpText = "鑽石場：需 矽晶T2 與 鐵系T2 (各扣 4 個)";
    else if (actionType === 'special_defense') helpText = "防災中心：需 鐵系T3(扣1) + 能源T3(扣2)";
    else if (actionType === 'special_omni') helpText = "萬能工廠：需 能源T3 (扣 3 個)";
    else if (actionType === 'special_accelerator') helpText = "加速器：需 鐵系T3(扣2) + 能源T3(扣2)";
    else if (actionType === 'buildFactory') helpText = "建造 T1 加工廠：需 2 種【不同】的 T0 物品 (各扣 3 個)";
    
    const descDiv = document.createElement("div");
    descDiv.style.gridColumn = "1 / -1";
    descDiv.style.color = "#f39c12";
    descDiv.style.marginBottom = "10px";
    descDiv.style.fontWeight = "bold";
    descDiv.innerText = helpText;
    grid.appendChild(descDiv);

    for (const [itemId, qty] of Object.entries(currentPlayerInventory)) {
        if (qty <= 0) continue;

        const btn = document.createElement("div");
        btn.className = "warehouse-item-btn";
        const itemName = itemsMeta[itemId]?.label || itemId;
        btn.innerText = `${itemName} (庫存: ${qty})`;
        
        btn.onclick = function() {
            if (btn.classList.contains("selected")) {
                btn.classList.remove("selected", "valid-selection", "invalid-selection");
                const index = selectedMaterials.indexOf(itemId);
                if (index > -1) selectedMaterials.splice(index, 1);
            } else {
                btn.classList.add("selected");
                selectedMaterials.push(itemId);
                
                // 觸發驗證機制
                const status = checkMaterialValidity(itemId, qty, pendingAction, pendingTargetId);
                if (status.valid) {
                    btn.classList.add("valid-selection");
                } else {
                    btn.classList.add("invalid-selection");
                    showToast(status.reason, "error");
                }
            }
            document.getElementById("confirm-warehouse-btn").disabled = (selectedMaterials.length === 0);
        };
        grid.appendChild(btn);
    }

    if (grid.children.length === 1) { // 只有提示文字，沒有按鈕
        grid.innerHTML += "<div style='color:#777; grid-column: 1 / -1; text-align: center;'>倉庫目前沒有物資可用</div>";
    }

    document.getElementById("warehouse-modal").classList.remove("hidden");
}

function closeWarehouseModal() {
    document.getElementById("warehouse-modal").classList.add("hidden");
    pendingAction = null;
    pendingTargetId = null;
    selectedMaterials = [];
}

async function submitWarehouseSelection() {
    if (pendingAction === 'buildFactory') {
        if (selectedMaterials.length < 2) return showToast("建造加工廠需至少選擇 2 種材料！", "error");
        await post("/api/build", {player_id: playerId, target_tier: 1, payment_materials: selectedMaterials}); 
    } else if (pendingAction === 'upgrade') {
        await post("/api/upgrade", {player_id: playerId, factory_id: pendingTargetId, payment_materials: selectedMaterials}); 
    } else if (pendingAction.startsWith('special_')) {
        const specialType = pendingAction; // 保留前綴，因為後端依賴 'special_diamond' 等字眼
        await post("/api/build_special", {player_id: playerId, building_type: specialType, payment_materials: selectedMaterials}); 
    }
    closeWarehouseModal();
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
        currentMarketPrices = state.market_prices;

        if (playerId && !state.player) {
            alert("遊戲已重置，請重新創立公司！", "系統通知");
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
        document.getElementById("ticker-text").innerText = tickerText + "      ///      " + tickerText;
    }

    const phaseNames = {1: "新聞階段", 2: "行動階段", 3: "交易階段", 4: "結算階段", 5: "遊戲結束"};
    const turnText = state.turn ? `(第 ${state.turn} 回合)` : "";
    document.getElementById("phase-display").innerText = `${phase}. ${phaseNames[phase] || "未知"} ${turnText}`;
    
    document.getElementById("action-panel").classList.toggle("hidden", phase !== 2);
    document.getElementById("trading-panel").classList.toggle("hidden", phase !== 3);

    // 更新政府收購介面
    if (govEvent && govEvent.targets) {
        let targetsHtml = "";
        let govOptions = "";
        govEvent.targets.forEach(t => {
            const meta = itemsMeta[t];
            const mPrice = currentMarketPrices[t] || meta.base_price;
            const gPrice = Math.floor(mPrice * 1.5);
            targetsHtml += `<div>🔸 ${meta.label}: 收購價 <span style="color:#2ecc71;">$${gPrice}</span> (市價 $${mPrice})</div>`;
            govOptions += `<option value="${t}">${meta.label} ($${gPrice})</option>`;
        });
        const targetList = document.getElementById("gov-target-list");
        if(targetList) targetList.innerHTML = targetsHtml;
        const tradeItem = document.getElementById("gov-trade-item");
        if(tradeItem) tradeItem.innerHTML = govOptions;
    } else {
        const targetList = document.getElementById("gov-target-list");
        if(targetList) targetList.innerHTML = "(本回合無收購案)";
        const tradeItem = document.getElementById("gov-trade-item");
        if(tradeItem) tradeItem.innerHTML = "";
    }

    if (state.player) {
        currentPlayerState = state.player;
        currentPlayerInventory = state.player.inventory; 
        
        document.getElementById("money-display").innerText = `$${state.player.money.toLocaleString()}`;
        document.getElementById("land-display").innerText = `土地: ${state.player.factories.length}/${state.player.land_limit}`;
        
        const invDiv = document.getElementById("inventory-list");
        const invHtml = Object.entries(state.player.inventory)
            .filter(([_, v]) => v > 0)
            .map(([k, v]) => `<div class="row"><span>${itemsMeta[k]?.label || k}</span> <span class="tag">x${v}</span></div>`)
            .join("");
        invDiv.innerHTML = invHtml || `<div style="color: #555; font-style: italic;">(倉庫是空的)</div>`;

        renderFactoriesSmart(state.player.factories, state.phase);
    }
    
    populateDropdown("trade-item", state.items_meta, state.market_prices, 1.0);
    const rawMaterialsMeta = {};
    for (const [k, v] of Object.entries(state.items_meta)) {
        if (v.tier === 0) rawMaterialsMeta[k] = v;
    }
    populateDropdown("bank-item", rawMaterialsMeta, state.market_prices, 0.85);

    const gameOverModal = document.getElementById("game-over-modal");
    if (state.final_ranking && state.player) {
        gameOverModal.style.display = "flex";
        // ... (保持結算邏輯不變) ...
        const myName = state.player.name;
        const rankingListBox = document.getElementById("global-ranking-list");
        let listHtml = "";

        // 生成排行榜
        state.final_ranking.forEach((playerObj, index) => {
            const rank = index + 1;
            const pName = playerObj.name;
            const scores = playerObj.scores;
            const totalScore = scores.total_score;

            if (pName === myName) {
                // 更新上方自己的專屬名次
                document.getElementById("my-final-rank").innerText = `你是第 ${rank} 名！`;
                document.getElementById("my-final-assets").innerHTML = 
                    `總資產: <b style="color: #4cd137;">$${totalScore.toLocaleString()}</b><br>` +
                    `<span style="font-size: 0.85em;">現金: $${scores.cash?.toLocaleString() || 0} | 庫存價值: $${scores.inventory_value?.toLocaleString() || 0} | 設施價值: $${scores.factory_value?.toLocaleString() || 0}</span>`;

                // 在排行榜中標記自己
                listHtml += `<div style="padding: 10px; color: #ff9800; font-weight: bold; border-bottom: 1px solid #333;">#${rank} ${pName} - $${totalScore.toLocaleString()} (你)</div>`;
            } else {
                listHtml += `<div style="padding: 10px; border-bottom: 1px solid #333; color: #ccc;">#${rank} ${pName} - $${totalScore.toLocaleString()}</div>`;
            }
        });

        rankingListBox.innerHTML = listHtml;
    } else {
        if(gameOverModal) gameOverModal.style.display = "none";
    }
}

function renderFactoriesSmart(factories, phase) {
    const list = document.getElementById("factory-list");
    
    if (list.children.length !== factories.length) {
        list.innerHTML = ""; 
        factories.forEach(f => {
            const div = document.createElement("div");
            div.className = "factory-box";
            div.id = `factory-box-${f.id}`; 
            
            div.dataset.tier = f.tier;            
            div.dataset.produced = f.has_produced ? "true" : "false"; 
            div.dataset.phase = phase;            
            
            div.innerHTML = generateFactoryInnerHtml(f, phase);
            list.appendChild(div);
            
            if(document.getElementById(`prod-${f.id}`)) checkRecipe(f.id);
        });
        return;
    }

    factories.forEach((f, index) => {
        const div = document.getElementById(`factory-box-${f.id}`);
        if (!div) return; 

        const tierChanged = div.dataset.tier != f.tier;
        const currentProducedStr = f.has_produced ? "true" : "false";
        const producedChanged = div.dataset.produced !== currentProducedStr;
        const phaseChanged = div.dataset.phase != phase;

        if (tierChanged || producedChanged || phaseChanged) {
            const selectEl = document.getElementById(`prod-${f.id}`);
            const oldVal = selectEl ? selectEl.value : null;
            const qtyEl = document.getElementById(`qty-${f.id}`);
            const oldQty = qtyEl ? qtyEl.value : null;

            div.innerHTML = generateFactoryInnerHtml(f, phase);
            
            div.dataset.tier = f.tier;
            div.dataset.produced = currentProducedStr;
            div.dataset.phase = phase;

            const newSelectEl = document.getElementById(`prod-${f.id}`);
            if (newSelectEl && oldVal) newSelectEl.value = oldVal;
            const newQtyEl = document.getElementById(`qty-${f.id}`);
            if (newQtyEl && oldQty) newQtyEl.value = oldQty;
        } 
        
        if (phase === 2 && document.getElementById(`prod-${f.id}`)) {
            checkRecipe(f.id);
        }
    });
}

function generateFactoryInnerHtml(f, phase) {
    let actionHtml = "";
    const isMiner = f.name.includes("Miner");
    const isSpecial = ["Diamond Mine", "Prophet", "Defense", "Omni Factory", "Accelerator"].includes(f.name);
    
    let demolishCost = 0;
    if (isMiner) demolishCost = 250; 
    else if (isSpecial) demolishCost = 4000;
    else {
        if (f.tier === 1) demolishCost = 500;
        else if (f.tier === 2) demolishCost = 1000;
        else if (f.tier === 3) demolishCost = 4000;
    }

    if (phase === 2) {
        // 🌟 鑽石場需要專屬的生產按鈕
        if (f.name === "Diamond Mine") {
            actionHtml = `
                <div class="row" style="gap:5px; margin-bottom: 5px;">
                    <input type="hidden" id="prod-${f.id}" value="diamond">
                    <input type="number" id="qty-${f.id}" value="1" min="1" style="flex:1; padding:8px;" placeholder="量">
                    <button class="btn btn-green" style="flex:1; margin:0;" onclick="produce('${f.id}')">💎 生產鑽石</button>
                </div>
            `;
        } else if (isSpecial) {
            actionHtml = `<div style="padding: 10px 0; color: #f1c40f; text-align: center; font-weight: bold; background: rgba(0,0,0,0.2); border-radius: 4px; margin-bottom: 5px;">⚡ 被動效果啟用中</div>`;
        } else if (isMiner) {
            if (f.has_produced) {
                actionHtml = `<span style="color: #aaa;">本回合已開採</span>`;
            } else {
                let options = "";
                for (const [code, meta] of Object.entries(itemsMeta)) {
                    if (meta.tier === 0) options += `<option value="${code}">${meta.label}</option>`;
                }
                actionHtml = `
                    <div class="row" style="gap:5px; margin-bottom: 5px;">
                        <select id="prod-${f.id}" style="flex:2;">${options}</select>
                        <input type="number" id="qty-${f.id}" value="1" min="1" style="flex:1; padding:8px;" placeholder="量">
                        <button class="btn btn-green" style="flex:1; margin:0;" onclick="produce('${f.id}')">開採</button>
                    </div>`;
            }
        } else {
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

        if (f.tier < 3 && !isSpecial) {
            let req = "";
            if (isMiner) {
                if (f.tier === 0) req = "需: 1種 T1產品(3個)"; 
                else if (f.tier === 1) req = "需: 1種 T2產品(3個)"; 
                else if (f.tier === 2) req = "需: 1種 T2(3個) + 1種 T1(3個)"; 
            } else {
                if (f.tier === 1) req = "需: 現金 $5,000 + 2種 T1產品(各5個)"; 
                else req = "需: 現金 $15,000 + 2種 T2(各3個) + 1種 T1(10個)"; 
            }
            actionHtml += `<button class="btn btn-orange" style="padding:6px; font-size:0.9em; margin-top:8px;" onclick="openWarehouseModal('upgrade', '${f.id}')">升級設施 (${req})</button>`;
        }
        
        actionHtml += `
            <button class="btn btn-red" style="padding:6px; font-size:0.9em; margin-top:8px;" onclick="demolish('${f.id}', ${demolishCost})">
                拆除設施 (花費 $${demolishCost})
            </button>
        `;
    } else {
        actionHtml = `<span style="color: #666; font-size: 0.9em;">等待行動階段...</span>`;
    }

    let displayName = f.name
        .replace("Miner", "採集器")
        .replace("Factory T1", "加工廠") 
        .replace("Factory", "加工廠")
        .replace("Diamond Mine", "鑽石場")
        .replace("Prophet", "預言家")
        .replace("Defense", "防災中心")
        .replace("Omni Factory", "萬能工廠")
        .replace("Accelerator", "加速器");
        
    return `
        <div class="row">
            <strong style="color: #fff;">${displayName}</strong>
            <span class="tag" style="background: ${f.tier===0?'#555':(f.tier===1?'#3498db':(f.tier===2?'#9b59b6':'#e67e22'))}">Lv.${f.tier}</span>
        </div>
        ${actionHtml}
    `;
}

function checkRecipe(factoryId) {
    const select = document.getElementById(`prod-${factoryId}`);
    const qtyInput = document.getElementById(`qty-${factoryId}`);
    const displayDiv = document.getElementById(`recipe-${factoryId}`);
    if(!select || !qtyInput || !displayDiv) return;

    const targetItem = select.value;
    if (!targetItem) { displayDiv.innerHTML = ""; return; }

    const quantity = parseInt(qtyInput.value) || 1;
    const itemData = itemsMeta[targetItem];
    if (!itemData || !itemData.recipe) { displayDiv.innerHTML = ""; return; }

    let html = `<div><strong>配方需求 (生產 x${quantity}):</strong></div>`;
    for (const [ingId, reqQty] of Object.entries(itemData.recipe)) {
        const totalReq = reqQty * quantity;
        const have = currentPlayerInventory[ingId] || 0;
        const meta = itemsMeta[ingId];
        const statusClass = have >= totalReq ? "recipe-ok" : "recipe-fail";
        const checkMark = have >= totalReq ? "(充足)" : "(不足)";
        html += `<span class="recipe-item ${statusClass}">${meta.label}: ${totalReq} (庫存: ${have}) ${checkMark}</span>`;
    }
    displayDiv.innerHTML = html;
}

function populateDropdown(elementId, meta, prices, priceRatio) {
    if (document.activeElement && document.activeElement.id === elementId) return;
    const sel = document.getElementById(elementId);
    if (!sel) return; 
    const currentVal = sel.value;
    let html = "";
    for (const [k, v] of Object.entries(meta)) {
        const marketP = (prices && prices[k] !== undefined) ? prices[k] : v.base_price;
        const finalP = Math.floor(marketP * priceRatio);
        html += `<option value="${k}">${v.label} ($${finalP})</option>`;
    }
    if (sel.innerHTML !== html) {
        sel.innerHTML = html;
        if(currentVal) sel.value = currentVal;
    }
}

async function produce(factoryId) {
    const item = document.getElementById(`prod-${factoryId}`).value;
    const qtyInput = document.getElementById(`qty-${factoryId}`);
    const qty = qtyInput ? (parseInt(qtyInput.value) || 1) : 1;
    await post("/api/produce", {player_id: playerId, factory_id: factoryId, target_item: item, quantity: qty});
}

function demolish(fid, cost) {
    showConfirm(`確定要拆除這座設施嗎？\n這將花費 $${cost} 的清潔費，且設施將永久消失！`, "拆除確認", 
        async function() { await post("/api/demolish", {player_id: playerId, factory_id: fid}); }
    );
}

async function sellToBank() {
    const item = document.getElementById("bank-item").value;
    const qty = parseInt(document.getElementById("bank-qty").value);
    if(!qty) return showToast("請輸入數量", "error");
    await post("/api/bank_sell", {player_id: playerId, item_id: item, quantity: qty});
}

async function submitOrder() {
    if (tradeMode === "MARKET") {
        const price = parseInt(document.getElementById("trade-price").value);
        const qty = parseInt(document.getElementById("trade-qty").value);
        if(!price || !qty) return showToast("請輸入有效的價格與數量", "error");
        await post("/api/trade", {
            player_id: playerId, type: document.getElementById("trade-type").value,
            item_id: document.getElementById("trade-item").value, price: price, quantity: qty
        });
    } else {
        const itemEl = document.getElementById("gov-trade-item");
        if(!itemEl) return;
        const itemId = itemEl.value;
        const qty = parseInt(document.getElementById("gov-trade-qty").value);
        if(!itemId || !qty) return showToast("請輸入有效的數量", "error");
        
        const marketP = currentMarketPrices[itemId] || itemsMeta[itemId].base_price;
        const govPrice = Math.floor(marketP * 1.5);
        
        await post("/api/trade", {
            player_id: playerId, type: "GOV_ASK", item_id: itemId, price: govPrice, quantity: qty
        });
    }
}

async function post(url, data) {
    try {
        const res = await fetch(url, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data) });
        const json = await res.json();
        if (res.status !== 200) {
            showToast("錯誤: " + (json.detail || "未知錯誤"), "error");
        } else {
            if (json.message) showToast("成功: " + json.message, "success");
            await fetchState();
        }
    } catch (e) { 
        showToast("連接失敗", "error"); 
    }
}
