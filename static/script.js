document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Element Selectors ---
    const loginBtn = document.getElementById('login-btn');
    const logoutBtn = document.getElementById('logout-btn');
    const loginStatus = document.getElementById('login-status');
    const qrcodeContainer = document.getElementById('qrcode-container');
    const qrcodeImg = document.getElementById('qrcode-img');
    const playlistsContainer = document.getElementById('playlists');
    const songListContainer = document.getElementById('song-list');
    const ongoingDownloadsList = document.getElementById('ongoing-downloads');
    const completedDownloadsList = document.getElementById('completed-downloads');
    const selectAllCompletedContainer = document.getElementById('select-all-completed-container');
    const selectAllCompletedCheckbox = document.getElementById('select-all-completed-checkbox');
    const completedActions = document.getElementById('completed-actions');

    // New selectors for ongoing tasks
    const selectAllOngoingContainer = document.getElementById('select-all-ongoing-container');
    const selectAllOngoingCheckbox = document.getElementById('select-all-ongoing-checkbox');
    const ongoingActions = document.getElementById('ongoing-actions');

    let loginCheckInterval;
    let currentTasks = {}; // 全局变量，存储最新的任务状态

    // --- Initial Setup ---
    checkInitialAuth();
    // Restore polling for all tasks
    setInterval(updateDownloadStatus, 2000);
    updateDownloadStatus(); // Initial call

    // --- Event Listeners ---
    loginBtn.addEventListener('click', handleLoginClick);
    logoutBtn.addEventListener('click', handleLogoutClick);

    // --- Functions ---

    async function handleLoginClick() {
        loginStatus.textContent = '正在获取二维码...';
        loginBtn.disabled = true;
        try {
            const response = await fetch('/api/login/qrcode');
            const data = await response.json();
            if (data.qrcode) {
                qrcodeImg.src = data.qrcode;
                qrcodeContainer.style.display = 'block';
                loginStatus.textContent = '请使用QQ音乐APP扫描二维码';
                loginCheckInterval = setInterval(checkLoginStatus, 2000);
            } else {
                loginStatus.textContent = '获取二维码失败，请重试。';
                loginBtn.disabled = false;
            }
        } catch (error) {
            console.error('获取二维码失败:', error);
            loginStatus.textContent = '获取二维码失败，请查看控制台了解详情。';
            loginBtn.disabled = false;
        }
    }

    async function checkLoginStatus() {
        try {
            const response = await fetch('/api/login/status');
            const data = await response.json();
            loginStatus.textContent = data.message;
            if (data.is_success) {
                clearInterval(loginCheckInterval);
                loginStatus.textContent = '登录成功！';
                loginBtn.style.display = 'none';
                logoutBtn.style.display = 'inline-block';
                qrcodeContainer.style.display = 'none';
                await getUserPlaylists();
            } else if (data.status === 'timeout') {
                clearInterval(loginCheckInterval);
                loginStatus.textContent = '二维码已过期，请重新获取。';
                loginBtn.disabled = false;
                qrcodeContainer.style.display = 'none';
            }
        } catch (error) {
            console.error('检查登录状态失败:', error);
            clearInterval(loginCheckInterval);
            loginStatus.textContent = '检查登录状态时出错。';
            loginBtn.disabled = false;
        }
    }

    async function handleLogoutClick() {
        try {
            await fetch('/api/logout', { method: 'POST' });
            window.location.reload();
        } catch (error) {
            console.error('退出登录失败:', error);
        }
    }

    async function checkInitialAuth() {
        try {
            const response = await fetch('/api/check-auth');
            const data = await response.json();
            if (data.is_logged_in) {
                loginStatus.textContent = '已恢复登录';
                loginBtn.style.display = 'none';
                logoutBtn.style.display = 'inline-block';
                await getUserPlaylists();
            } else {
                loginStatus.textContent = '未登录';
                loginBtn.style.display = 'inline-block';
                logoutBtn.style.display = 'none';
            }
        } catch (error) {
            console.error('检查初始登录状态失败:', error);
        }
    }

    async function getUserPlaylists() {
        // ... (This function remains the same as before)
        try {
            const response = await fetch('/api/playlists');
            const playlists = await response.json();
            if (playlists.error) {
                playlistsContainer.innerHTML = `<p class="text-danger">获取歌单失败: ${playlists.error}</p>`;
                return;
            }
            if (playlists.length === 0) {
                playlistsContainer.innerHTML = '<p>你还没有创建或收藏任何歌单。</p>';
                return;
            }
            const createdPlaylists = playlists.filter(p => p.type === 'created');
            const favoritePlaylists = playlists.filter(p => p.type === 'favorite');
            let finalHtml = '';
            const renderPlaylist = (pl) => `
                <div class="list-group-item d-flex justify-content-between align-items-center">
                    <a href="#" class="playlist-item flex-grow-1" data-id="${pl.dissid}" style="text-decoration: none; color: inherit;">
                        ${pl.title} <span class="badge bg-secondary float-end">${pl.subtitle || ''}</span>
                    </a>
                    <button class="btn btn-outline-primary btn-sm ms-2 monitor-btn" data-id="${pl.dissid}" title="监控歌单更新">
                        <i class="bi bi-eye"></i>
                    </button>
                </div>
            `;
            if (createdPlaylists.length > 0) {
                finalHtml += '<h6><i class="bi bi-music-note-list"></i> 自建歌单</h6>';
                finalHtml += `<div class="list-group mb-3">${createdPlaylists.map(renderPlaylist).join('')}</div>`;
            }
            if (favoritePlaylists.length > 0) {
                finalHtml += '<h6><i class="bi bi-heart-fill"></i> 收藏歌单</h6>';
                finalHtml += `<div class="list-group">${favoritePlaylists.map(renderPlaylist).join('')}</div>`;
            }
            playlistsContainer.innerHTML = finalHtml;
            setupPlaylistListeners();
            updateMonitorButtons();
        } catch (error) {
            console.error('获取歌单失败:', error);
            playlistsContainer.innerHTML = '<p class="text-danger">获取歌单时发生错误。</p>';
        }
    }

    function setupPlaylistListeners() {
        // ... (This function remains the same as before)
        document.querySelectorAll('.playlist-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                document.querySelectorAll('.list-group-item').forEach(i => i.classList.remove('active'));
                item.closest('.list-group-item').classList.add('active');
                const playlistId = item.dataset.id;
                getSongsInPlaylist(playlistId);
            });
        });
        document.querySelectorAll('.monitor-btn').forEach(button => {
            button.addEventListener('click', async (e) => {
                const playlistId = e.currentTarget.dataset.id;
                e.currentTarget.disabled = true;
                try {
                    const response = await fetch(`/api/monitor/${playlistId}`, { method: 'POST' });
                    const data = await response.json();
                    if (data.status === 'success') {
                        updateMonitorButtons();
                    } else {
                        alert(`操作失败: ${data.message}`);
                    }
                } catch (error) {
                    console.error('监控操作失败:', error);
                } finally {
                    e.currentTarget.disabled = false;
                }
            });
        });
    }

    async function updateMonitorButtons() {
        // ... (This function remains the same as before)
        try {
            const response = await fetch('/api/monitor/status');
            const monitoredIds = await response.json();
            document.querySelectorAll('.monitor-btn').forEach(button => {
                const playlistId = button.dataset.id;
                if (monitoredIds.includes(playlistId)) {
                    button.classList.remove('btn-outline-primary');
                    button.classList.add('btn-primary', 'active');
                    button.innerHTML = '<i class="bi bi-eye-fill"></i>';
                    button.title = "取消监控";
                } else {
                    button.classList.remove('btn-primary', 'active');
                    button.classList.add('btn-outline-primary');
                    button.innerHTML = '<i class="bi bi-eye"></i>';
                    button.title = "监控歌单更新";
                }
            });
        } catch (error) {
            console.error('更新监控状态失败:', error);
        }
    }

    // --- Song List & Download Logic (remains mostly the same) ---
    let allSongs = [];
    let loadedSongsCount = 0;
    const songsPerLoad = 30;

    async function getSongsInPlaylist(playlistId) {
        // ... (This function remains the same as before)
        songListContainer.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div></div>';
        allSongs = [];
        loadedSongsCount = 0;
        songListContainer.onscroll = null;
        try {
            const response = await fetch(`/api/playlist/${playlistId}`);
            const songs = await response.json();
            if (songs.error) {
                songListContainer.innerHTML = `<p class="text-danger">获取歌曲失败: ${songs.error}</p>`;
                return;
            }
            if (songs.length === 0) {
                songListContainer.innerHTML = '<p>这个歌单里没有歌曲。</p>';
                return;
            }
            allSongs = songs;
            songListContainer.innerHTML = `
                <div class="d-grid gap-2 mb-2">
                    <button class="btn btn-success" id="download-all-btn" data-playlist-id="${playlistId}">
                        <i class="bi bi-download"></i> 全部下载 (${allSongs.length}首)
                    </button>
                </div>
                <ul class="list-group"></ul>
            `;
            loadMoreSongs();
            document.getElementById('download-all-btn').addEventListener('click', async (e) => {
                const button = e.currentTarget;
                button.textContent = '正在加入队列...';
                button.disabled = true;
                try {
                    await fetch(`/api/playlist/download/${playlistId}`, { method: 'POST' });
                    alert('已将歌单中所有未下载的歌曲加入下载队列。');
                } catch (error) {
                    console.error('完整下载歌单失败:', error);
                    alert('操作失败，请查看控制台。');
                } finally {
                    button.textContent = `全部下载 (${allSongs.length}首)`;
                    button.disabled = false;
                }
            });
            songListContainer.onscroll = () => {
                if (songListContainer.scrollTop + songListContainer.clientHeight >= songListContainer.scrollHeight - 200) {
                    loadMoreSongs();
                }
            };
        } catch (error) {
            console.error('获取歌曲列表失败:', error);
            songListContainer.innerHTML = '<p class="text-danger">获取歌曲列表时发生错误。</p>';
        }
    }

    function loadMoreSongs() {
        if (loadedSongsCount >= allSongs.length) return;
        const songListUl = songListContainer.querySelector('ul');
        const songsToLoad = allSongs.slice(loadedSongsCount, loadedSongsCount + songsPerLoad);
        const songsHtml = songsToLoad.map(song => `
            <li class="list-group-item d-flex justify-content-between align-items-center song-item" data-song-mid="${song.mid}">
                <span>${song.name} - ${song.singer.map(s => s.name).join('/')}</span>
                <button class="btn btn-primary btn-sm download-btn">下载</button>
            </li>
        `).join('');
        songListUl.innerHTML += songsHtml;
        loadedSongsCount += songsToLoad.length;

        // 为新加载的按钮设置初始状态并附加事件
        const newItems = Array.from(songListUl.children).slice(-songsToLoad.length);
        newItems.forEach(item => {
            const button = item.querySelector('.download-btn');
            const songMid = item.dataset.songMid;
            const task = currentTasks[songMid];
            
            // 设置初始状态
            updateSongButtonState(button, task);

            // 附加事件监听器
            button.addEventListener('click', (e) => {
                const songItem = e.target.closest('.song-item');
                const songName = songItem.querySelector('span').textContent;
                button.textContent = '队列中';
                button.disabled = true;
                startDownload(songMid, songName);
            });
        });
    }

    async function startDownload(songMid, songName) {
        // ... (This function remains the same as before)
        try {
            await fetch(`/api/download/${songMid}?song_name=${encodeURIComponent(songName)}`, { method: 'POST' });
        } catch (error) {
            console.error('启动下载失败:', error);
        }
    }

    // --- MODIFIED Download Status Logic ---

    async function updateDownloadStatus() {
        const selectedOngoingMids = new Set(
            Array.from(document.querySelectorAll('.ongoing-task-checkbox:checked')).map(cb => cb.value)
        );
        const selectedCompletedMids = new Set(
            Array.from(document.querySelectorAll('.completed-task-checkbox:checked')).map(cb => cb.value)
        );

        try {
            const response = await fetch('/api/download/status');
            currentTasks = await response.json(); // 更新全局任务状态
            const tasks = currentTasks;
            const ongoingTasks = [];
            const completedTasks = [];

            for (const mid in tasks) {
                const taskWithMid = { ...tasks[mid], mid };
                if (tasks[mid].status === 'completed') {
                    completedTasks.push(taskWithMid);
                } else {
                    ongoingTasks.push(taskWithMid);
                }
            }

            // Sort ongoing tasks: downloading > queued > others, then by original order (newest first)
            const statusPriority = { 'downloading': 1, 'queued': 2 };
            ongoingTasks.sort((a, b) => {
                const priorityA = statusPriority[a.status] || 3;
                const priorityB = statusPriority[b.status] || 3;
                if (priorityA !== priorityB) {
                    return priorityA - priorityB;
                }
                // If priorities are the same, newest (later in original array) comes first
                // We need original indices, but since we don't have them, we can assume
                // the server sends them in a somewhat consistent order. Reversing the original
                // list before processing is a good proxy for "newest first".
                // Let's stick to reversing the completed list for now as that's less critical.
                return 0; // Keep original relative order for same-status tasks for now
            });

            completedTasks.reverse();

            // Update ongoing list
            if (ongoingTasks.length === 0) {
                ongoingDownloadsList.innerHTML = '<li class="list-group-item">暂无进行中的任务</li>';
            } else {
                ongoingDownloadsList.innerHTML = ongoingTasks.map(task => createTaskItemHtml(task, false)).join('');
            }

            // Update ongoing list UI
            if (ongoingTasks.length === 0) {
                ongoingDownloadsList.innerHTML = '<li class="list-group-item">暂无进行中的任务</li>';
                selectAllOngoingContainer.style.display = 'none';
                ongoingActions.style.display = 'none';
            } else {
                ongoingDownloadsList.innerHTML = ongoingTasks.map(task => createTaskItemHtml(task)).join('');
                selectAllOngoingContainer.style.display = 'flex';
            }

            // Add "Retry All Failed" button if there are any failed tasks
            const failedTasksCount = ongoingTasks.filter(t => t.status === 'failed').length;
            const retryAllBtnContainer = document.getElementById('retry-all-container'); // Assuming a container exists
            if (retryAllBtnContainer) {
                if (failedTasksCount > 0) {
                    retryAllBtnContainer.innerHTML = `
                        <button class="btn btn-warning btn-sm" id="retry-all-failed-btn">
                            <i class="bi bi-arrow-clockwise"></i> 重试所有失败 (${failedTasksCount})
                        </button>`;
                    document.getElementById('retry-all-failed-btn').addEventListener('click', retryAllFailed);
                } else {
                    retryAllBtnContainer.innerHTML = '';
                }
            }

            // Update completed list UI
            if (completedTasks.length === 0) {
                completedDownloadsList.innerHTML = '<li class="list-group-item">暂无已完成的任务</li>';
                selectAllCompletedContainer.style.display = 'none';
                completedActions.style.display = 'none';
            } else {
                completedDownloadsList.innerHTML = completedTasks.map(task => createTaskItemHtml(task)).join('');
                selectAllCompletedContainer.style.display = 'flex';
            }

            // Restore selection states
            selectedOngoingMids.forEach(mid => {
                const checkbox = document.querySelector(`.ongoing-task-checkbox[value="${mid}"]`);
                if (checkbox) checkbox.checked = true;
            });
            selectedCompletedMids.forEach(mid => {
                const checkbox = document.querySelector(`.completed-task-checkbox[value="${mid}"]`);
                if (checkbox) checkbox.checked = true;
            });
            
            updateSelectionState();

            // --- NEW: Update song list buttons based on task status ---
            document.querySelectorAll('.song-item').forEach(item => {
                const mid = item.dataset.songMid;
                const button = item.querySelector('.download-btn');
                if (button) {
                    updateSongButtonState(button, tasks[mid]);
                }
            });

        } catch (error) {
            console.error("Error updating download status:", error);
        }
    }

    function updateSongButtonState(button, task) {
        if (!button) return;

        if (task) {
            switch (task.status) {
                case 'completed':
                    button.textContent = '已下载';
                    button.disabled = true;
                    button.className = 'btn btn-success btn-sm download-btn';
                    break;
                case 'downloading':
                    button.textContent = `下载中 (${task.progress || 0}%)`;
                    button.disabled = true;
                    button.className = 'btn btn-secondary btn-sm download-btn';
                    break;
                case 'queued':
                    button.textContent = '队列中';
                    button.disabled = true;
                    button.className = 'btn btn-secondary btn-sm download-btn';
                    break;
                case 'failed':
                    button.textContent = '失败';
                    button.disabled = true; // Or enable for retry
                    button.className = 'btn btn-danger btn-sm download-btn';
                    break;
                default:
                    button.textContent = '下载';
                    button.disabled = false;
                    button.className = 'btn btn-primary btn-sm download-btn';
            }
        } else {
            // If no task exists for this song, ensure button is in default state
            button.textContent = '下载';
            button.disabled = false;
            button.className = 'btn btn-primary btn-sm download-btn';
        }
    }

    function createTaskItemHtml(task) {
        let statusContent = '';
        let actionButtons = '';
        let errorReason = '';
        const isCompleted = task.status === 'completed';
        const checkboxClass = isCompleted ? 'completed-task-checkbox' : 'ongoing-task-checkbox';

        const checkboxHtml = `
            <div class="form-check me-3">
                <input class="form-check-input ${checkboxClass}" type="checkbox" value="${task.mid}" id="task-${task.mid}">
            </div>`;

        switch (task.status) {
            case 'downloading':
                statusContent = `<div class="progress" style="height: 20px;"><div class="progress-bar" role="progressbar" style="width: ${task.progress || 0}%;">${task.progress || 0}%</div></div>`;
                actionButtons = `<button class="btn btn-warning btn-sm ms-2 cancel-btn" data-mid="${task.mid}" title="取消"><i class="bi bi-x-lg"></i></button>`;
                break;
            case 'completed':
                statusContent = `<span class="badge bg-success">已完成</span>`;
                break;
            case 'failed':
                statusContent = `<span class="badge bg-danger">下载失败</span>`;
                errorReason = `<div class="text-danger small mt-1">${task.error || '未知错误'}</div>`;
                actionButtons = `<button class="btn btn-info btn-sm ms-2 retry-btn" data-mid="${task.mid}" title="重试"><i class="bi bi-arrow-clockwise"></i></button><button class="btn btn-danger btn-sm ms-2 remove-btn" data-mid="${task.mid}" title="移除"><i class="bi bi-trash"></i></button>`;
                break;
            case 'queued':
                 statusContent = `<span class="badge bg-secondary">队列中</span>`;
                 actionButtons = `<button class="btn btn-warning btn-sm ms-2 cancel-btn" data-mid="${task.mid}" title="取消"><i class="bi bi-x-lg"></i></button>`;
                 break;
            case 'cancelled':
                statusContent = `<span class="badge bg-dark">已取消</span>`;
                actionButtons = `<button class="btn btn-danger btn-sm ms-2 remove-btn" data-mid="${task.mid}" title="移除"><i class="bi bi-trash"></i></button>`;
                break;
            default:
                statusContent = `<span class="badge bg-dark">${task.status}</span>`;
        }
        const qualityBadge = task.quality ? `<span class="badge bg-info me-2">${task.quality}</span>` : '';
        return `
            <li class="list-group-item">
                <div class="d-flex justify-content-between align-items-center">
                    ${checkboxHtml}
                    <label class="form-check-label flex-grow-1 text-truncate" for="task-${task.mid}" title="${task.song_name}" style="cursor: pointer;">
                        ${task.song_name}
                    </label>
                    <div class="d-flex align-items-center">
                        ${qualityBadge}
                        <div style="width: 100px;">${statusContent}</div>
                        ${actionButtons}
                    </div>
                </div>
                ${errorReason}
            </li>`;
    }

    // --- Selection & Action Logic ---
    function updateSelectionState() {
        // Handle ongoing tasks selection
        const ongoingCheckboxes = document.querySelectorAll('.ongoing-task-checkbox');
        const checkedOngoing = document.querySelectorAll('.ongoing-task-checkbox:checked');
        ongoingActions.style.display = checkedOngoing.length > 0 ? 'block' : 'none';
        
        if (ongoingCheckboxes.length > 0 && checkedOngoing.length === ongoingCheckboxes.length) {
            selectAllOngoingCheckbox.checked = true;
            selectAllOngoingCheckbox.indeterminate = false;
        } else if (checkedOngoing.length > 0) {
            selectAllOngoingCheckbox.checked = false;
            selectAllOngoingCheckbox.indeterminate = true;
        } else {
            selectAllOngoingCheckbox.checked = false;
            selectAllOngoingCheckbox.indeterminate = false;
        }

        // Handle completed tasks selection
        const completedCheckboxes = document.querySelectorAll('.completed-task-checkbox');
        const checkedCompleted = document.querySelectorAll('.completed-task-checkbox:checked');
        completedActions.style.display = checkedCompleted.length > 0 ? 'block' : 'none';

        if (completedCheckboxes.length > 0 && checkedCompleted.length === completedCheckboxes.length) {
            selectAllCompletedCheckbox.checked = true;
            selectAllCompletedCheckbox.indeterminate = false;
        } else if (checkedCompleted.length > 0) {
            selectAllCompletedCheckbox.checked = false;
            selectAllCompletedCheckbox.indeterminate = true;
        } else {
            selectAllCompletedCheckbox.checked = false;
            selectAllCompletedCheckbox.indeterminate = false;
        }
    }

    selectAllOngoingCheckbox.addEventListener('change', (e) => {
        document.querySelectorAll('.ongoing-task-checkbox').forEach(checkbox => {
            checkbox.checked = e.target.checked;
        });
        updateSelectionState();
    });

    selectAllCompletedCheckbox.addEventListener('change', (e) => {
        document.querySelectorAll('.completed-task-checkbox').forEach(checkbox => {
            checkbox.checked = e.target.checked;
        });
        updateSelectionState();
    });

    async function retryAllFailed() {
        const btn = document.getElementById('retry-all-failed-btn');
        if (!btn) return;
        
        btn.textContent = '正在重试...';
        btn.disabled = true;
        try {
            const response = await fetch('/api/downloads/retry_all_failed', { method: 'POST' });
            const data = await response.json();
            alert(data.message || '操作完成');
            updateDownloadStatus();
        } catch (error) {
            console.error('全部重试失败:', error);
            alert('操作失败，请查看控制台。');
        } finally {
            // The button will be rebuilt by updateDownloadStatus, so no need to re-enable it here.
        }
    }

    document.body.addEventListener('click', async (e) => {
        const target = e.target;

        // If a checkbox is clicked, just update the state
        if (target.matches('.ongoing-task-checkbox, .completed-task-checkbox')) {
            updateSelectionState();
            return;
        }

        const actionTarget = target.closest('.retry-btn, .cancel-btn, .remove-btn, .bulk-action-btn, .bulk-action-btn-ongoing');
        if (!actionTarget) return;

        // Handle ongoing bulk actions
        if (actionTarget.matches('.bulk-action-btn-ongoing')) {
            e.preventDefault();
            const selectedMids = Array.from(document.querySelectorAll('.ongoing-task-checkbox:checked')).map(cb => cb.value);
            if (selectedMids.length === 0) {
                alert('请至少选择一个进行中的任务。');
                return;
            }
            const action = actionTarget.dataset.action; // 'cancel' or 'remove'
            const confirmMessage = `确定要对选中的 ${selectedMids.length} 个任务执行 "${action === 'cancel' ? '取消' : '移除'}" 操作吗？`;
            
            if (confirm(confirmMessage)) {
                for (const mid of selectedMids) {
                    try {
                        await fetch(`/api/download/${action}/${mid}`, { method: 'POST' });
                    } catch (error) {
                        console.error(`批量操作失败 for mid ${mid}:`, error);
                    }
                }
                updateDownloadStatus();
            }
            return;
        }

        // Handle completed bulk actions
        if (actionTarget.matches('.bulk-action-btn')) {
            e.preventDefault();
            const selectedMids = Array.from(document.querySelectorAll('.completed-task-checkbox:checked')).map(cb => cb.value);
            if (selectedMids.length === 0) {
                alert('请至少选择一个任务。');
                return;
            }
            const deleteFiles = actionTarget.dataset.deleteFiles === 'true';
            let confirmMessage = `确定要从列表中移除选中的 ${selectedMids.length} 个任务吗？`;
            if (deleteFiles) {
                confirmMessage = `【高危操作】\n\n确定要移除并永久删除选中的 ${selectedMids.length} 个文件吗？\n\n此操作不可恢复！`;
            }
            if (confirm(confirmMessage)) {
                try {
                    await fetch('/api/downloads/remove_selected', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ mids: selectedMids, delete_files: deleteFiles })
                    });
                    updateDownloadStatus();
                } catch (error) {
                    console.error('批量操作失败:', error);
                }
            }
            return;
        }
        actionTarget.disabled = true;
        const mid = actionTarget.dataset.mid;
        let actionUrl = '';
        if (actionTarget.matches('.retry-btn')) actionUrl = `/api/download/retry/${mid}`;
        if (actionTarget.matches('.cancel-btn')) actionUrl = `/api/download/cancel/${mid}`;
        if (actionTarget.matches('.remove-btn')) actionUrl = `/api/download/remove/${mid}`;
        
        if(actionUrl) {
            try {
                await fetch(actionUrl, { method: 'POST' });
                updateDownloadStatus();
            } catch (error) {
                console.error('操作失败:', error);
            }
        }
        setTimeout(() => {
            if (actionTarget) actionTarget.disabled = false;
        }, 500);
    });
});
