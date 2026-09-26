
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
const sharedContentButton = document.getElementById('shared-content-button');
const sharedContentModal = document.getElementById('shared-content-modal');
const closeSharedContentButton = document.getElementById('close-shared-content');
const sharedContentList = document.getElementById('shared-content-list');
const previewModal = document.getElementById('preview-modal');
const previewStage = document.getElementById('preview-stage');
const previewTitle = document.getElementById('preview-title');
const previewKind = document.getElementById('preview-kind');
const previewOpen = document.getElementById('preview-open');
const previewDownload = document.getElementById('preview-download');
const closePreviewButton = document.getElementById('close-preview');
const carouselControls = document.getElementById('carousel-controls');
const carouselCounter = document.getElementById('carousel-counter');
const previousImageButton = document.getElementById('previous-image');
const nextImageButton = document.getElementById('next-image');

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
let sharedContent = { images: [], documents: [], links: [] };
let activeSharedTab = 'images';
let activeImageIndex = 0;

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

function safeResourceUrl(value, allowBlob) {
    try {
        const url = new URL(value, window.location.origin);
        const allowed = ['http:', 'https:'];
        if (allowBlob) allowed.push('blob:');
        return allowed.includes(url.protocol) ? url.href : '';
    } catch (error) {
        return '';
    }
}

function urlAttribute(value, allowBlob) {
    return escapeHtml(safeResourceUrl(value, allowBlob));
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
function normaliseAttachment(att) {
    return {
        id: att.id || '',
        file_url: att.file_url,
        original_filename: att.original_filename || 'Arquivo',
        attachment_type: (att.attachment_type || 'other').toLowerCase()
    };
}

function attachmentMarkup(att) {
    const item = normaliseAttachment(att);
    const fileUrl = urlAttribute(item.file_url || '', true);
    if (!fileUrl) return '';
    const filename = escapeHtml(item.original_filename);
    if (item.attachment_type === 'image') {
        return `<button type="button" class="attachment-preview-button" data-preview-kind="image" data-preview-url="${fileUrl}" data-preview-name="${filename}"><img src="${fileUrl}" alt="${filename}"></button>`;
    }
    if (item.attachment_type === 'video') return `<video src="${fileUrl}" controls preload="metadata"></video>`;
    if (item.attachment_type === 'audio') return `<audio src="${fileUrl}" controls preload="metadata"></audio>`;
    if (item.attachment_type === 'pdf') {
        return `<button type="button" class="pdf-attachment-card" data-preview-kind="pdf" data-preview-url="${fileUrl}" data-preview-name="${filename}"><span class="file-icon">PDF</span><span>${filename}</span></button>`;
    }
    return `<a href="${fileUrl}" target="_blank" rel="noopener" download="${filename}"><span class="file-icon">▤</span><span>${filename}</span></a>`;
}

function createLocalAttachmentsHtml(attachments) {
    return `<div class="attachments">${attachments.map(att => `<div class="attachment-in-message">${attachmentMarkup(att)}</div>`).join('')}</div>`;
}

async function createAttachmentsHtml(attachments) {
    return createLocalAttachmentsHtml(attachments);
}

function extractLinks(text) {
    return (text || '').match(/https?:\/\/[^\s<>"']+/g) || [];
}

function trackMessageContent(data) {
    const base = { message_id: data.message_id || data.temp_id, author: data.author || username, timestamp: data.timestamp };
    (data.attachments || []).forEach(function (raw) {
        const attachment = Object.assign({}, base, normaliseAttachment(raw));
        const list = attachment.attachment_type === 'image' ? sharedContent.images : sharedContent.documents;
        if (!list.some(item => item.id && attachment.id && item.id === attachment.id)) list.unshift(attachment);
    });
    extractLinks(data.content || data.message).forEach(function (url) {
        if (!sharedContent.links.some(item => item.url === url && item.message_id === base.message_id)) sharedContent.links.unshift(Object.assign({}, base, { url: url, label: url }));
    });
    updateSharedCounts();
}

function updateSharedCounts() {
    ['images', 'documents', 'links'].forEach(function (kind) {
        const counter = document.getElementById(kind + '-count');
        if (counter) counter.textContent = sharedContent[kind].length;
    });
}

function formatSharedDate(timestamp) {
    if (!timestamp) return '';
    return new Date(timestamp).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
}

function renderSharedContent() {
    if (!sharedContentList) return;
    const items = sharedContent[activeSharedTab] || [];
    if (!items.length) {
        const labels = { images: 'Nenhuma imagem compartilhada.', documents: 'Nenhum documento compartilhado.', links: 'Nenhum link compartilhado.' };
        sharedContentList.innerHTML = `<div class="empty-shared">${labels[activeSharedTab]}</div>`;
        return;
    }
    if (activeSharedTab === 'images') {
        sharedContentList.innerHTML = `<div class="shared-grid">${items.map((item, index) => `<button class="shared-image" type="button" data-gallery-index="${index}" title="${escapeHtml(item.original_filename)}"><img src="${urlAttribute(item.file_url)}" alt="${escapeHtml(item.original_filename)}"></button>`).join('')}</div>`;
        return;
    }
    if (activeSharedTab === 'links') {
        sharedContentList.innerHTML = items.map(item => `<div class="shared-row"><span class="shared-row-icon">↗</span><span class="shared-row-copy"><a href="${urlAttribute(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.label)}</a><small>${escapeHtml(item.author)} · ${formatSharedDate(item.timestamp)}</small></span><span class="shared-row-actions"><a class="secondary-button" href="${urlAttribute(item.url)}" target="_blank" rel="noopener">Abrir</a></span></div>`).join('');
        return;
    }
    sharedContentList.innerHTML = items.map(item => {
        const isPdf = item.attachment_type === 'pdf';
        return `<div class="shared-row"><span class="shared-row-icon">${isPdf ? 'PDF' : '▤'}</span><span class="shared-row-copy"><strong>${escapeHtml(item.original_filename)}</strong><small>${escapeHtml(item.author)} · ${formatSharedDate(item.timestamp)}</small></span><span class="shared-row-actions">${isPdf ? `<button class="secondary-button" type="button" data-preview-kind="pdf" data-preview-url="${urlAttribute(item.file_url)}" data-preview-name="${escapeHtml(item.original_filename)}">Ler</button>` : ''}<a class="secondary-button" href="${urlAttribute(item.file_url)}" download target="_blank" rel="noopener">Baixar</a></span></div>`;
    }).join('');
}

async function openSharedContent() {
    if (!sharedContentModal) return;
    sharedContentModal.style.display = 'flex';
    if (chatApp.dataset.historyEnabled === 'true') {
        sharedContentList.innerHTML = '<div class="conversation-state">Carregando conteúdo...</div>';
        try {
            const response = await fetch(`/message/${roomIdRandom}/shared/`);
            if (!response.ok) throw new Error('Falha ao carregar conteúdo');
            sharedContent = await response.json();
        } catch (error) {
            sharedContentList.innerHTML = '<div class="empty-shared">Não foi possível carregar o conteúdo compartilhado.</div>';
            return;
        }
    }
    updateSharedCounts();
    renderSharedContent();
}

function closeSharedContent() { if (sharedContentModal) sharedContentModal.style.display = 'none'; }

function openPreview(kind, url, name, imageIndex) {
    if (!previewModal) return;
    previewTitle.textContent = name || 'Visualização';
    previewKind.textContent = kind === 'pdf' ? 'DOCUMENTO PDF' : 'IMAGEM';
    previewOpen.href = url;
    previewDownload.href = url;
    previewDownload.setAttribute('download', name || 'arquivo');
    previewStage.innerHTML = '';
    if (kind === 'pdf') {
        const frame = document.createElement('iframe');
        frame.src = url;
        frame.title = 'Leitor de ' + (name || 'PDF');
        previewStage.appendChild(frame);
        carouselControls.hidden = true;
    } else {
        activeImageIndex = typeof imageIndex === 'number' ? imageIndex : Math.max(0, sharedContent.images.findIndex(item => item.file_url === url));
        renderActiveImage(url, name);
    }
    previewModal.style.display = 'flex';
}

function renderActiveImage(fallbackUrl, fallbackName) {
    const item = sharedContent.images[activeImageIndex];
    const url = item ? item.file_url : fallbackUrl;
    const name = item ? item.original_filename : fallbackName;
    previewStage.innerHTML = `<img src="${urlAttribute(url, true)}" alt="${escapeHtml(name || 'Imagem')}">`;
    previewTitle.textContent = name || 'Imagem';
    previewOpen.href = url;
    previewDownload.href = url;
    carouselControls.hidden = sharedContent.images.length < 2;
    carouselCounter.textContent = sharedContent.images.length ? `${activeImageIndex + 1} de ${sharedContent.images.length}` : '';
}

function moveCarousel(direction) {
    if (!sharedContent.images.length) return;
    activeImageIndex = (activeImageIndex + direction + sharedContent.images.length) % sharedContent.images.length;
    renderActiveImage();
}

function closePreview() { if (previewModal) previewModal.style.display = 'none'; previewStage.innerHTML = ''; }

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
                        const pendingContentId = pending.getAttribute('data-temp-id') || data.temp_id;
                        sharedContent.images = sharedContent.images.filter(item => item.message_id !== pendingContentId);
                        sharedContent.documents = sharedContent.documents.filter(item => item.message_id !== pendingContentId);
                        trackMessageContent(data);
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
    trackMessageContent(data);

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
        roomMeta.textContent = 'Conversa privada';
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
        closeSharedContent();
        closePreview();
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

if (sharedContentButton) sharedContentButton.addEventListener('click', openSharedContent);
if (closeSharedContentButton) closeSharedContentButton.addEventListener('click', closeSharedContent);
if (closePreviewButton) closePreviewButton.addEventListener('click', closePreview);
if (previousImageButton) previousImageButton.addEventListener('click', function () { moveCarousel(-1); });
if (nextImageButton) nextImageButton.addEventListener('click', function () { moveCarousel(1); });
document.addEventListener('click', function (event) {
    const preview = event.target.closest('[data-preview-kind]');
    if (preview) openPreview(preview.dataset.previewKind, preview.dataset.previewUrl, preview.dataset.previewName);
    const galleryItem = event.target.closest('[data-gallery-index]');
    if (galleryItem) {
        const index = Number(galleryItem.dataset.galleryIndex);
        const item = sharedContent.images[index];
        if (item) openPreview('image', item.file_url, item.original_filename, index);
    }
    const tab = event.target.closest('[data-shared-tab]');
    if (tab) {
        activeSharedTab = tab.dataset.sharedTab;
        document.querySelectorAll('.shared-tab').forEach(button => button.classList.toggle('active', button === tab));
        renderSharedContent();
    }
});

window.onclick = function(event) {
    if (event.target == sharedContentModal) closeSharedContent();
    if (event.target == previewModal) closePreview();
    if (event.target == membersModal) {
        closeMembersModal();
    }
    const deleteModal = document.getElementById("deleteModal");
    if (event.target == deleteModal) {
        closeDeleteModal();
    }
}

chatInput.addEventListener('focus', markMessagesAsRead);
