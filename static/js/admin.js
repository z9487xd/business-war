let lastPrices = {};

async function updateStatus() {
    try {
        const res = await fetch("/admin/data");
        const data = await res.json();
        
        // 1. 顯示階段與回合 (中文化)
        // 後端傳來的 phase 是數字 1, 2, 3, 4
        const phaseNames = {1: "新聞階段", 2: "行動階段", 3: "交易階段", 4: "結算階段"};
        const phaseName = phaseNames[data.phase] || "未知";
        
        document.getElementById("current-phase").innerText = `階段 ${data.phase}: ${phaseName}`;
        document.getElementById("current-turn").innerText = `第 ${data.turn} 回合`;

        // 2. 更新市場價格表
        if(data.market_prices || data.items_meta) {
             // 這裡假設我們有個方式取得 items_meta，或是後端 admin/data 已經包含了
             // 如果沒有，通常建議在 admin/data 裡一起回傳 items_meta
             // 為了保險，這裡做個簡單的檢查
             const prices = data.market_prices || {};
             // 為了拿到中文名稱，我們可能需要呼叫一次 /api/state 或是讓 admin/data 回傳 items_meta
             // 這裡假設您已經在 main.py 的 /admin/data 加入了 items_meta
             // 如果還沒，這裡先用 key 顯示
             const meta = data.items_meta || {}; 
             updateMarketTable(prices, meta);
        }

        // 3. 更新玩家排行榜
        const playerHtml = data.players.map((p, index) => {
            return `<tr>
                <td style="text-align: center;">#${index + 1}</td>
                <td style="font-weight: bold;">${p.name}</td>
                <td class="money-col">$${p.money.toLocaleString()}</td>
                <td class="center-col">${p.land}</td>
                <td class="center-col">${p.inventory_count}</td>
            </tr>`;
        }).join("");
        document.getElementById("player-table").innerHTML = playerHtml;

        // 4. 更新日誌
        const logWindow = document.getElementById("log-window");
        if (data.logs) {
            const logsHtml = data.logs.map(log => {
                const match = log.match(/^\[(.*?)\] (.*)/);
                if (match) {
                    return `<div class="log-entry"><span class="log-time">${match[1]}</span> ${match[2]}</div>`;
                }
                return `<div class="log-entry">${log}</div>`;
            }).join("");
            
            if (logWindow.innerHTML !== logsHtml) {
                logWindow.innerHTML = logsHtml;
            }
        }

    } catch (e) {
        console.error("Connection lost", e);
    }
}

function updateMarketTable(prices, meta) {
    const marketHtml = Object.entries(prices).map(([k, p]) => {
        // 嘗試取得中文名稱，如果沒有則顯示代碼
        const itemLabel = meta[k] ? meta[k].label : k;
        const oldP = lastPrices[k] || p;
        
        let trendClass = "same";
        if (p > oldP) trendClass = "up";
        else if (p < oldP) trendClass = "down";
        
        lastPrices[k] = p; 

        return `<tr>
            <td>${itemLabel}</td>
            <td class="price-tag ${trendClass}">$${p}</td>
        </tr>`;
    }).join("");
    
    const tbody = document.getElementById("market-table").querySelector("tbody");
    if(tbody.innerHTML !== marketHtml) {
        tbody.innerHTML = marketHtml;
    }
}

async function nextPhase() { 
    if(!confirm("確定要進入「下一階段」嗎？\n這將推進遊戲進度。")) return;
    await fetch("/admin/next_phase", {method: "POST"}); 
    updateStatus(); 
}

async function resetGame() { 
    if(!confirm("⚠️ 警告：確定要「重置遊戲」嗎？\n所有玩家數據將被清空，無法復原！")) return;
    await fetch("/admin/reset", {method: "POST"}); 
    updateStatus(); 
}

setInterval(updateStatus, 1000);
updateStatus();