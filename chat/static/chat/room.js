
const chatApp = document.getElementById('chat-app');
const chatLogContainer = document.getElementById('chat-log-container');
const chatInput = document.getElementById('chat-message-input');
const chatSubmit = document.getElementById('chat-message-submit');
const chatRoomList = document.getElementById('chat-room-list');
const markAsReadButton = document.getElementById('mark-as-read-button');
const roomSearch = document.getElementById('room-search');
const noResults = document.getElementById('no-results');
const openSidebarButton = document.getElementById('open-sidebar');
const closeSidebarButton = document.getElementById('close-sidebar');
const sidebarBackdrop = document.getElementById('sidebar-backdrop');

// Modal
const membersButton = document.getElementById('members-button');
const membersModal = document.getElementById('members-modal');
const closeButton = document.querySelector('.close-button');

// Anexos e Gravação
const attachButton = document.getElementById('attach-button');
const attachmentInput = document.getElementById('attachment-input');
const attachmentPreviewContainer = document.getElementById('attachment-preview-container');
const recordAudioButton = document.getElementById('record-audio-button');
let attachedFiles = [];
let mediaRecorder;
let audioChunks = [];

// Variáveis de contexto do Django
const roomIdRandom = chatApp.dataset.roomId;
const roomName = chatApp.dataset.roomName;
const username = chatApp.dataset.username;
const userId = Number(chatApp.dataset.userId);
const tempId = Date.now().toString();

function escapeHtml(value) {
    const element = document.createElement('div');
    element.textContent = value == null ? '' : String(value);
    return element.innerHTML;
}

const chatSocket = new WebSocket(
    (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws/chat/' + roomIdRandom + '/'
);

// Função para checar acessibilidade (já boa, mas adicionei um timeout pra evitar travar em requests lentos)
async function checkAttachmentAccessibility(url) {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000); // 5s timeout

        const response = await fetch(url, {
            method: 'HEAD',
            signal: controller.signal
        });

        clearTimeout(timeoutId);
        return response.ok; // true se 2xx
    } catch (error) {
        console.warn(`Erro ao verificar acessibilidade do anexo ${url}:`, error);
        return false; // Erro de rede, timeout ou CORS → considera inacessível
    }
}

// Versão síncrona para preview local (sem check, pois URLs locais sempre funcionam)
function createLocalAttachmentsHtml(attachments) {
    let html = '';
    for (const att of attachments) {
        const fileUrl = att.file_url; // URL.createObjectURL local
        const filename = escapeHtml(att.original_filename);
        const attachmentType = att.attachment_type.toLowerCase();

        html += `<div class="attachment-in-message">`;
        if (attachmentType === 'image') {
            html += `<a href="${fileUrl}" target="_blank"><img src="${fileUrl}" alt="${filename}" style="max-width:200px; max-height:200px; border-radius:8px;"></a>`;
        } else if (attachmentType === 'video') {
            html += `<video src="${fileUrl}" controls style="max-width:300px; border-radius:8px;"></video>`;
        } else if (attachmentType === 'audio') {
            html += `<audio src="${fileUrl}" controls style="width:100%;"></audio>`;
        } else if (attachmentType === 'pdf' || attachmentType === 'document') {
            html += `<a href="${fileUrl}" target="_blank" download="${filename}">
                        <span class="file-icon">📄</span>
                        <span>${filename}</span>
                     </a>`;
        } else {
            html += `<a href="${fileUrl}" target="_blank" download="${filename}">
                        <span class="file-icon">📄</span>
                        <span>${filename}</span>
                     </a>`;
        }
        html += `</div>`;
    }
    return `<div class="attachments">${html}</div>`;
}

// Versão async para anexos do servidor (com check)
async function createAttachmentsHtml(attachments) {
    let html = '';
    for (const att of attachments) {
        const fileUrl = att.file_url;
        const filename = escapeHtml(att.original_filename);
        const attachmentType = att.attachment_type.toLowerCase();
        const attachmentId = att.id;

        const isAccessible = await checkAttachmentAccessibility(fileUrl);

        html += `<div class="attachment-in-message">`;
        if (!isAccessible) {
            html += `<span class="file-icon" style="color: red;">⚠️</span>
                     <span style="color: red; font-style: italic;">Anexo não encontrado: ${filename}</span>
                     <br><small style="color: gray;">(Pode ter sido removido ou há um erro de acesso)</small>`;
        } else if (attachmentType === 'image') {
            html += `<a href="${fileUrl}" target="_blank"><img src="${fileUrl}" alt="${filename}" style="max-width:200px; max-height:200px; border-radius:8px;"></img></a>`;
        } else if (attachmentType === 'video') {
            html += `<video src="${fileUrl}" controls style="max-width:300px; border-radius:8px;"></video>`;
        } else if (attachmentType === 'audio') {
            html += `<audio src="${fileUrl}" controls style="width:100%;"></audio>`;
        } else if (attachmentType === 'pdf' || attachmentType === 'document') {
            html += `<a href="${fileUrl}" target="_blank" download="${filename}">
                        <span class="file-icon">📄</span>
                        <span>${filename}</span>
                     </a>`;
        } else {
            html += `<a href="${fileUrl}" target="_blank" download="${filename}">
                        <span class="file-icon">📄</span>
                        <span>${filename}</span>
                     </a>`;
        }

        html += `</div>`;
    }
    return `<div class="attachments">${html}</div>`;
}

// Buscar histórico de mensagens (agora async e com await)
async function fetchMessageHistory() {
    try {
        const response = await fetch(`/message/${roomIdRandom}/messages/`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const history = await response.json();

        chatLogContainer.innerHTML = '';
        if (history.length === 0) {
            const emptyText = chatApp.dataset.historyEnabled === 'true'
                ? 'Nenhuma mensagem nesta sala ainda. Seja o primeiro a conversar.'
                : 'O histórico está desabilitado. Você verá apenas mensagens enviadas durante esta sessão.';
            chatLogContainer.innerHTML = `<div class="conversation-state">${emptyText}</div>`;
        } else {
            for (const message of history) { // Loop síncrono, mas await dentro da func
                await addMessageToLog(message);
            }
        }
        scrollToBottom();
    } catch (error) {
        console.error("Erro ao carregar histórico de mensagens:", error);
        chatLogContainer.innerHTML = '<div class="message system">Ocorreu um erro ao carregar o histórico. Por favor, recarregue a página.</div>';
    }
}

// WebSocket Events
chatSocket.onmessage = function(e) {
    const data = JSON.parse(e.data);
    handleWebSocketMessage(data);
};

chatSocket.onopen = function() {
    console.log('Conexão WebSocket estabelecida');
    chatApp.classList.add('is-connected');
};

chatSocket.onclose = function() {
    console.log('Conexão WebSocket fechada');
    chatApp.classList.remove('is-connected');
};

chatSocket.onerror = function(error) {
    console.error('Erro WebSocket:', error);
};

// Função de busca de salas
function filterRooms(searchTerm) {
    const rooms = document.querySelectorAll('.chat-room-item');
    let hasResults = false;

    rooms.forEach(room => {
        const roomNameAttr = room.getAttribute('data-room-name').toLowerCase();
        if (roomNameAttr.includes(searchTerm.toLowerCase())) {
            room.style.display = 'flex';
            hasResults = true;
        } else {
            room.style.display = 'none';
        }
    });
    noResults.style.display = hasResults ? 'none' : 'block';
}

roomSearch.addEventListener('input', function(e) {
    filterRooms(e.target.value);
});

// Manipulador de mensagens WebSocket (agora async)
async function handleWebSocketMessage(data) {
    switch(data.type) {
        case 'chat_message':
            if (data.temp_id) {
                // Procurar mensagem pendente pelo temp_id
                const pending = document.querySelector(`[data-temp-id="${data.temp_id}"]`);
                if (pending) {
                    // Atualizar atributos
                    pending.setAttribute('data-message-id', data.message_id);
                    pending.removeAttribute('data-temp-id');

                    // Atualizar timestamp e remover "(enviando...)"
                    const smallTag = pending.querySelector('small');
                    if (smallTag) {
                        smallTag.textContent = formatTimestamp(data.timestamp);
                    }

                    // Atualizar conteúdo final (se backend modificou algo)
                    const pTag = pending.querySelector('p');
                    if (pTag) {
                        pTag.textContent = data.message || data.content || '';
                    }

                    // Re-render anexos do servidor (com check de acessibilidade)
                    if (data.attachments && data.attachments.length > 0) {
                        const attachmentsHtml = await createAttachmentsHtml(data.attachments);
                        const existingAttachments = pending.querySelector('.attachments');
                        if (existingAttachments) {
                            existingAttachments.outerHTML = attachmentsHtml; // Substitui o preview local pelo real
                        } else {
                            pending.innerHTML += attachmentsHtml; // Adiciona se não existir
                        }
                    }
                } else {
                    // Se não encontrar pendente, adiciona normalmente (com await)
                    await addMessageToLog(data);
                }
            } else {
                // Mensagem recebida de outro usuário → adiciona normalmente
                await addMessageToLog(data);
            }
            break;

        case 'user_activity':
            handleUserActivity(data);
            break;
        case 'unread_count_update':
            updateUnreadCounts(data.room_data);
            break;
        case 'user_left':
            handleUserLeft(data);
            break;
        case 'room_deleted':
            handleRoomDeleted(data);
            break;
        case 'error':
            showError(data.message);
            break;
    }
}


function handleRoomDeleted(data) {
    const div = document.createElement('div');
    div.classList.add('message', 'system');
    div.innerHTML = `A sala "${data.room_name}" foi excluída. Você será redirecionado.<br><small>${formatTimestamp(new Date().toISOString())}</small>`;
    const state = chatLogContainer.querySelector('.conversation-state');
    if (state) state.remove();
    chatLogContainer.appendChild(div);
    scrollToBottom();
    setTimeout(() => {
        window.location.href = '/chat/';
    }, 1000);
}

function handleUserLeft(data) {
    const div = document.createElement('div');
    div.classList.add('message', 'system');
    div.innerHTML = `${data.username} saiu da sala.<br><small>${formatTimestamp(new Date().toISOString())}</small>`;
    const state = chatLogContainer.querySelector('.conversation-state');
    if (state) state.remove();
    chatLogContainer.appendChild(div);
    scrollToBottom();
    if (data.username === username) {
        setTimeout(() => {
            window.location.href = '/chat/';
        }, 1000);
    }
}

// Funções de manipulação de mensagens (agora ASYNC!)
async function addMessageToLog(data) {
    console.log('addMessageToLog data:', data);

    // Evitar duplicados
    if (data.message_id && document.querySelector(`[data-message-id="${data.message_id}"]`)) {
        return;
    }
    if (data.temp_id && document.querySelector(`[data-temp-id="${data.temp_id}"]`)) {
        return;
    }

    const div = document.createElement('div');
    const messageContent = escapeHtml(data.content || data.message || '');
    const authorName = escapeHtml(data.author || '');

    // Detecta se é preview local (temp_id presente e attachments com URL.createObjectURL-like)
    const isLocalPreview = data.temp_id && data.attachments && data.attachments.some(att => att.file_url.startsWith('blob:'));

    let attachmentsHtml = '';
    if (data.attachments && data.attachments.length > 0) {
        if (isLocalPreview) {
            // Usa versão síncrona para preview local (rápido, sem check)
            attachmentsHtml = createLocalAttachmentsHtml(data.attachments);
        } else {
            // Para histórico e mensagens do servidor: async com check
            attachmentsHtml = await createAttachmentsHtml(data.attachments);
        }
    }

    if (data.is_system_message) {
        div.classList.add('message', 'system');
        div.innerHTML = `
            ${messageContent}<br>
            <small>${formatTimestamp(data.timestamp)}</small>
        `;
    } else {
        div.classList.add('message');
        div.classList.add(data.author === username ? 'self' : 'other');
        div.innerHTML = `
            <strong>${authorName}:</strong>
            <p>${messageContent}</p>
            ${attachmentsHtml}
            <small>${formatTimestamp(data.timestamp)} ${data.status === 'pending' ? '(enviando...)' : ''}</small>
        `;
    }

    if (data.message_id) {
        div.setAttribute('data-message-id', data.message_id);
    }
    if (data.temp_id) {
        div.setAttribute('data-temp-id', data.temp_id);
    }

    const state = chatLogContainer.querySelector('.conversation-state');
    if (state) state.remove();
    chatLogContainer.appendChild(div);
    scrollToBottom();
}

// Funções de UI
function scrollToBottom() {
    chatLogContainer.scrollTop = chatLogContainer.scrollHeight;
}

function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function updateUnreadCounts(roomData) {
    renderSidebar(roomData);
}

function renderSidebar(roomData) {
    chatRoomList.innerHTML = '';
    if (!roomData || roomData.length === 0) {
        chatRoomList.innerHTML = '<div class="no-rooms">Nenhuma sala disponível</div>';
        return;
    }

    roomData.forEach(room => {
        const roomLink = document.createElement('a');
        roomLink.href = `/chat/${room.id_random}/`;
        roomLink.className = 'chat-room-item';
        roomLink.setAttribute('data-room-name', room.name);
        if (room.id_random === roomIdRandom) {
            roomLink.classList.add('active');
        }
        const avatar = document.createElement('span');
        avatar.className = 'conversation-avatar';
        avatar.textContent = (room.name || '?').charAt(0).toUpperCase();

        const copy = document.createElement('span');
        copy.className = 'conversation-copy';
        const roomNameElement = document.createElement('span');
        roomNameElement.className = 'room-name';
        roomNameElement.textContent = room.name;
        const roomMeta = document.createElement('span');
        roomMeta.className = 'conversation-meta';
        roomMeta.textContent = room.is_private ? 'Conversa privada' : 'Espaço da equipe';
        copy.appendChild(roomNameElement);
        copy.appendChild(roomMeta);
        roomLink.appendChild(avatar);
        roomLink.appendChild(copy);
        if (room.unread_count > 0) {
            const unread = document.createElement('span');
            unread.className = 'unread-count';
            unread.textContent = room.unread_count;
            roomLink.appendChild(unread);
        }
        chatRoomList.appendChild(roomLink);
    });
}

// Funções de interação
function markMessagesAsRead() {
    chatSocket.send(JSON.stringify({ type: 'mark_as_read' }));
    const unreadBadges = document.querySelectorAll('.unread-count');
    unreadBadges.forEach(badge => badge.remove());
}

function handleUserActivity(data) {
    console.log('Atividade do usuário:', data);
}

function showError(message) {
    console.error('Erro:', message);
    alert('Erro: ' + message);
}

// Funções de anexo e gravação (mantidas iguais)
attachButton.addEventListener('click', () => attachmentInput.click());

attachmentInput.addEventListener('change', (e) => {
    attachedFiles = Array.from(e.target.files).filter(file => file.size <= 5 * 1024 * 1024);
    if (e.target.files.length !== attachedFiles.length) {
        alert('Alguns arquivos foram ignorados por excederem o limite de 5MB.');
    }
    renderAttachedFiles();
});

function renderAttachedFiles() {
    attachmentPreviewContainer.innerHTML = '';
    attachmentPreviewContainer.hidden = attachedFiles.length === 0;

    attachedFiles.forEach((file, index) => {
        const item = document.createElement('div');
        item.className = 'attachment-item';
        item.setAttribute('data-index', index);

        const removeBtn = document.createElement('span');
        removeBtn.className = 'remove-btn';
        removeBtn.textContent = 'x';
        removeBtn.addEventListener('click', () => {
            removeAttachedFile(index);
        });

        const fileInfo = document.createElement('span');
        fileInfo.className = 'file-info';
        fileInfo.textContent = file.name;

        const fileType = file.type.split('/')[0];
        let previewElement;
        if (fileType === 'image') {
            previewElement = document.createElement('img');
            previewElement.src = URL.createObjectURL(file);
            previewElement.style.maxWidth = '100px';
            previewElement.style.maxHeight = '100px';
        } else if (fileType === 'video') {
            previewElement = document.createElement('video');
            previewElement.src = URL.createObjectURL(file);
            previewElement.controls = true;
            previewElement.style.maxWidth = '100px';
        } else if (fileType === 'audio') {
            previewElement = document.createElement('audio');
            previewElement.src = URL.createObjectURL(file);
            previewElement.controls = true;
        } else {
            previewElement = document.createElement('span');
            previewElement.className = 'file-icon';
            previewElement.textContent = '📄';
        }

        item.appendChild(removeBtn);
        item.appendChild(previewElement);
        item.appendChild(fileInfo);
        attachmentPreviewContainer.appendChild(item);
    });
}

function removeAttachedFile(index) {
    attachedFiles.splice(index, 1);
    renderAttachedFiles();
}

recordAudioButton.addEventListener('click', async () => {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
        recordAudioButton.textContent = '🎙️';
        recordAudioButton.style.backgroundColor = '';
        return;
    }
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        mediaRecorder.ondataavailable = event => audioChunks.push(event.data);
        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const audioFile = new File([audioBlob], `gravacao_${Date.now()}.webm`, { type: 'audio/webm' });
            if (audioFile.size <= 5 * 1024 * 1024) {
                attachedFiles.push(audioFile);
                renderAttachedFiles();
            } else {
                alert('Gravação de áudio excede o limite de 5MB.');
            }
        };
        mediaRecorder.start();
        recordAudioButton.textContent = '🔴';
        recordAudioButton.style.backgroundColor = 'red';
    } catch (err) {
        console.error('Erro ao acessar o microfone:', err);
        alert('Não foi possível acessar o microfone. Verifique as permissões.');
    }
});

// Envio de mensagem (agora async, com await no addMessageToLog)
async function sendMessage() {
    const msg = chatInput.value.trim();
    if (msg === '' && attachedFiles.length === 0) return;

    chatSubmit.disabled = true;
    chatSubmit.textContent = '...';

    // 🔹 ID temporário (frontend)
    const tempId = Date.now() + '-' + Math.random().toString(36).substring(2, 9);

    // 🔹 Criar objetos para a pré-visualização local
    const localAttachmentsForPreview = attachedFiles.map(file => ({
        file_url: URL.createObjectURL(file), // URL local temporária
        original_filename: file.name,
        attachment_type: file.type.split('/')[0]
    }));

    // 🔹 Exibir mensagem local imediatamente (com preview local, sem check)
    await addMessageToLog({
        temp_id: tempId,
        author: username,
        content: msg, // Usar 'content' para consistência
        attachments: localAttachmentsForPreview,
        timestamp: new Date().toISOString(),
        status: 'pending' // Indica que está sendo enviada
    });

    // 🔹 Preparar dados para o backend (converter para Base64)
    let attachmentsToSend = [];
    try {
        for (const file of attachedFiles) {
            const fileData = await fileToBase64(file);
            attachmentsToSend.push({
                filename: file.name,
                data: fileData
            });
        }
    } catch (error) {
        console.error('Erro ao converter arquivos para base64:', error);
        alert('Erro ao processar anexos. Tente novamente.');
        // Aqui você pode remover a mensagem pendente se desejar
        const pendingMsg = document.querySelector(`[data-temp-id="${tempId}"]`);
        if (pendingMsg) pendingMsg.remove();

        chatSubmit.disabled = false;
        chatSubmit.textContent = '▶️';
        return;
    }

    // 🔹 Enviar para backend
    chatSocket.send(JSON.stringify({
        type: 'chat_message',
        message: msg,
        attachments: attachmentsToSend,
        temp_id: tempId // Enviar o temp_id
    }));

    // Limpar UI
    chatInput.value = '';
    attachedFiles = [];
    renderAttachedFiles();
    chatInput.focus();

    chatSubmit.disabled = false;
    chatSubmit.textContent = '▶️';
}


function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = error => reject(error);
    });
}

chatSubmit.addEventListener('click', sendMessage);
chatInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        sendMessage();
    }
});


// Inicialização (agora com await no fetch)
document.addEventListener('DOMContentLoaded', async function() {
    await fetchMessageHistory();
    chatInput.focus();

    chatRoomList.addEventListener('click', function(event) {
        const roomItem = event.target.closest('.chat-room-item');
        if (roomItem) {
            event.preventDefault();
            markMessagesAsRead();
            setTimeout(() => {
                window.location.href = roomItem.href;
            }, 100);
        }
    });
});

function setSidebarOpen(isOpen) {
    document.body.classList.toggle('sidebar-open', isOpen);
}

if (openSidebarButton) openSidebarButton.addEventListener('click', () => setSidebarOpen(true));
if (closeSidebarButton) closeSidebarButton.addEventListener('click', () => setSidebarOpen(false));
if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', () => setSidebarOpen(false));

// Navegação por teclado
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'k') {
        e.preventDefault();
        chatInput.focus();
    }
    if (e.key === 'Escape') {
        chatInput.value = '';
        chatInput.blur();
    }
});

// Funções do Modal
function openMembersModal() {
    if (membersModal) membersModal.style.display = 'flex';
}

function closeMembersModal() {
    if (membersModal) membersModal.style.display = 'none';
}

function openDeleteModal() {
    const modal = document.getElementById("deleteModal");
    if (modal) modal.style.display = "flex";
}

function closeDeleteModal() {
    const modal = document.getElementById("deleteModal");
    if (modal) modal.style.display = "none";
}

if (membersButton) membersButton.addEventListener('click', openMembersModal);
if (closeButton) closeButton.addEventListener('click', closeMembersModal);

window.onclick = function(event) {
    if (event.target == membersModal) {
        closeMembersModal();
    }
    const deleteModal = document.getElementById("deleteModal");
    if (event.target == deleteModal) {
        closeDeleteModal();
    }
}

chatInput.addEventListener('focus', markMessagesAsRead);
