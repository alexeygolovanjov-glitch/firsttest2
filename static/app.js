const state = {
  library: [],
  searchResults: [],
  selected: null,
  selectedPlayer: null,
  loadingPlayersFor: null,
  token: localStorage.getItem('adminToken') || '',
  searchTimer: null
}

const moviesEl = document.querySelector('#movies')
const detailsEl = document.querySelector('#details')
const searchInput = document.querySelector('#searchInput')
const statusFilter = document.querySelector('#statusFilter')
const movieDialog = document.querySelector('#movieDialog')
const movieForm = document.querySelector('#movieForm')
const tokenStatus = document.querySelector('#tokenStatus')
const toast = document.querySelector('#toast')

const statusLabels = {
  none: 'Без списка',
  planned: 'В планах',
  watching: 'Смотрю',
  watched: 'Просмотрено',
  favorite: 'Любимое'
}

function headers() {
  return {
    'Content-Type': 'application/json',
    ...(state.token ? { 'X-Admin-Token': state.token } : {})
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...headers(), ...(options.headers || {}) }
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }
  return response.json()
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]
  })
}

function showToast(message, type = 'ok') {
  toast.textContent = message
  toast.className = `toast visible ${type}`
  window.clearTimeout(showToast.timeout)
  showToast.timeout = window.setTimeout(() => {
    toast.className = 'toast'
  }, 3200)
}

function updateTokenStatus() {
  tokenStatus.textContent = state.token ? 'Токен задан' : 'Токен не задан'
  tokenStatus.classList.toggle('active', Boolean(state.token))
}

async function runAdminAction(action, successMessage) {
  try {
    await action()
    showToast(successMessage)
  } catch (error) {
    const message = String(error.message || '')
    if (message.includes('401')) {
      showToast('Токен не подошел. Проверь ADMIN_TOKEN в .env', 'error')
      return
    }
    showToast('Ошибка: действие не выполнено', 'error')
    console.error(error)
  }
}

function currentItems() {
  return searchInput.value.trim() ? state.searchResults : state.library
}

function posterFor(movie) {
  return movie.poster_url || '/assets/poster-placeholder.svg'
}

async function loadLibrary() {
  const params = new URLSearchParams()
  params.set('status', statusFilter.value)
  state.library = await api(`/api/movies?${params.toString()}`)
  renderMovies()
  if (!state.selected && state.library[0]) selectLibraryMovie(state.library[0].id)
}

async function searchRemote(query) {
  if (query.length < 2) {
    state.searchResults = []
    renderMovies()
    return
  }

  moviesEl.innerHTML = '<p class="muted">Ищу фильмы...</p>'
  try {
    state.searchResults = await api(`/api/search?query=${encodeURIComponent(query)}&limit=8`)
    renderMovies()
    if (state.searchResults[0]) selectSearchMovie(state.searchResults[0].kp_id)
  } catch (error) {
    const message = String(error.message || '')
    if (message.includes('KINOPOISK_API_KEY')) {
      moviesEl.innerHTML = '<p class="error">На сервере не задан KINOPOISK_API_KEY.</p>'
      return
    }
    moviesEl.innerHTML = '<p class="error">Поиск сейчас не ответил.</p>'
    console.error(error)
  }
}

function renderMovies() {
  const items = currentItems()
  const isSearch = Boolean(searchInput.value.trim())

  if (!items.length) {
    moviesEl.innerHTML = `<p class="muted">${isSearch ? 'Ничего не найдено.' : 'В библиотеке пока пусто.'}</p>`
    return
  }

  moviesEl.innerHTML = items
    .map((movie) => {
      const id = isSearch ? movie.kp_id : movie.id
      const active =
        state.selected?.mode === (isSearch ? 'search' : 'library') && String(state.selected.id) === String(id)
      const playerInfo = isSearch
        ? 'Кинопоиск'
        : statusLabels[movie.list_status] || 'Без списка'
      return `
        <button class="movie-tile ${active ? 'active' : ''}" data-id="${escapeHtml(id)}" data-mode="${isSearch ? 'search' : 'library'}">
          <img src="${escapeHtml(posterFor(movie))}" alt="" loading="lazy" />
          <span>${escapeHtml(movie.title)}</span>
          <small>${escapeHtml(movie.year || 'Без года')} · ${escapeHtml(playerInfo)}</small>
        </button>
      `
    })
    .join('')
}

async function selectLibraryMovie(id) {
  const movie = await api(`/api/movies/${id}`)
  state.selected = { mode: 'library', id, movie }
  state.selectedPlayer = movie.player_url
    ? { name: 'Сохранённый плеер', iframe: movie.player_url, source: 'saved' }
    : null
  renderMovies()
  renderDetails()
}

function selectSearchMovie(kpId) {
  const movie = state.searchResults.find((item) => String(item.kp_id) === String(kpId))
  if (!movie) return
  state.selected = { mode: 'search', id: kpId, movie }
  state.selectedPlayer = null
  renderMovies()
  renderDetails()
  loadPlayersForSearchMovie(kpId)
}

function playerMarkup() {
  if (state.loadingPlayersFor && state.selected?.mode === 'search') {
    return '<div class="no-player">Ищу плееры...</div>'
  }
  if (!state.selectedPlayer?.iframe) return '<div class="no-player">Плеер не найден</div>'
  return `<iframe src="${escapeHtml(state.selectedPlayer.iframe)}" title="Плеер" allowfullscreen></iframe>`
}

async function loadPlayersForSearchMovie(kpId) {
  state.loadingPlayersFor = String(kpId)
  renderDetails()
  try {
    const payload = await api(`/api/players/${encodeURIComponent(kpId)}`)
    const players = payload.players || []
    const stillSelected = state.selected?.mode === 'search' && String(state.selected.id) === String(kpId)
    const movie = state.searchResults.find((item) => String(item.kp_id) === String(kpId))
    if (!movie) return
    movie.players = players
    movie.player_message = payload.message || ''
    if (stillSelected) {
      state.selected.movie = movie
      state.selectedPlayer = players[0] || null
    }
  } catch (error) {
    const movie = state.searchResults.find((item) => String(item.kp_id) === String(kpId))
    if (movie) movie.player_message = 'Не удалось получить плееры'
    console.error(error)
  } finally {
    if (String(state.loadingPlayersFor) === String(kpId)) state.loadingPlayersFor = null
    renderMovies()
    renderDetails()
  }
}

function playerSelect(movie) {
  const players = selectedPlayers()
  if (state.loadingPlayersFor && state.selected?.mode === 'search') {
    return '<div class="player-select-row"><span class="muted">Ищу плееры KinoBD...</span></div>'
  }
  if (!players.length) {
    return `<div class="player-select-row"><span class="muted">${escapeHtml(movie.player_message || 'Плееры не найдены.')}</span></div>`
  }

  return `
    <div class="player-select-row">
      <select id="playerSelect" aria-label="Выбор плеера">
        ${players
          .map(
            (player, index) => `
              <option value="${index}" ${state.selectedPlayer?.iframe === player.iframe ? 'selected' : ''}>
                ${escapeHtml(player.name || player.translate || `Плеер ${index + 1}`)}
              </option>
            `
          )
          .join('')}
      </select>
    </div>
  `
}

function renderDetails() {
  if (!state.selected) {
    detailsEl.innerHTML = `
      <div class="empty-state">
        <span>Найди фильм</span>
        <p>Начни вводить название, и плееры появятся автоматически.</p>
      </div>
    `
    return
  }

  const movie = state.selected.movie
  const canSave = state.selected.mode === 'search'

  detailsEl.innerHTML = `
    ${playerSelect(movie)}
    <div class="player">${playerMarkup()}</div>
    <div class="detail-body">
      <p class="eyebrow">${escapeHtml(movie.genre || 'Фильм')}</p>
      <h2>${escapeHtml(movie.title)}</h2>
      <p class="meta">${escapeHtml(movie.year || 'Без года')} ${movie.rating ? `· ${movie.rating}/10` : ''}</p>
      <p>${escapeHtml(movie.description || 'Описание пока не добавлено.')}</p>
      ${movie.source_url ? `<a class="source-link" href="${escapeHtml(movie.source_url)}" target="_blank" rel="noreferrer">Источник</a>` : ''}

      <section class="player-tools">
        <div>
          <h3>${escapeHtml(state.selected.mode === 'search' ? 'Результат поиска' : 'В библиотеке')}</h3>
          <p>${escapeHtml(movie.kinopoisk_id || movie.kp_id || '')}</p>
        </div>
        ${canSave ? '<button id="saveSearchMovie" type="button">Сохранить</button>' : ''}
      </section>

      ${
        state.selected.mode === 'library'
          ? `
            <div class="controls-row">
              <select id="listSelect">
                ${Object.entries(statusLabels)
                  .map(([value, label]) => `<option value="${value}" ${movie.list_status === value ? 'selected' : ''}>${label}</option>`)
                  .join('')}
              </select>
              <input id="ratingInput" type="number" min="1" max="10" value="${movie.rating || ''}" placeholder="1-10" />
              <button id="saveRating">Оценить</button>
            </div>
            <label class="note-label">Заметка<textarea id="noteInput" rows="4">${escapeHtml(movie.note || '')}</textarea></label>
            <button id="saveNote">Сохранить заметку</button>
          `
          : ''
      }
    </div>
  `

  bindDetailActions()
}

function selectedPlayers() {
  if (state.selected?.mode === 'search') return state.selected.movie.players || []
  return state.selectedPlayer ? [state.selectedPlayer] : []
}

function bindDetailActions() {
  document.querySelector('#playerSelect')?.addEventListener('change', (event) => {
    const players = selectedPlayers()
    state.selectedPlayer = players[Number(event.target.value)] || null
    renderDetails()
  })

  document.querySelector('#saveSearchMovie')?.addEventListener('click', async () => {
    const movie = state.selected.movie
    await runAdminAction(async () => {
      const saved = await api('/api/movies', {
        method: 'POST',
        body: JSON.stringify({
          kinopoisk_id: movie.kp_id,
          title: movie.title,
          original_title: movie.original_title || '',
          year: movie.year ? Number(movie.year) : null,
          description: movie.description || '',
          poster_url: movie.poster_url || '',
          player_url: state.selectedPlayer?.iframe || '',
          source_url: movie.kp_id ? `https://www.kinopoisk.ru/film/${movie.kp_id}/` : '',
          genre: movie.genre || ''
        })
      })
      await loadLibrary()
      await selectLibraryMovie(saved.id)
    }, 'Фильм сохранён')
  })

  if (state.selected?.mode !== 'library') return
  const movieId = state.selected.id

  document.querySelector('#listSelect')?.addEventListener('change', async (event) => {
    await runAdminAction(async () => {
      await api(`/api/movies/${movieId}/list`, {
        method: 'PUT',
        body: JSON.stringify({ status: event.target.value })
      })
      await selectLibraryMovie(movieId)
    }, 'Статус сохранён')
  })

  document.querySelector('#saveRating')?.addEventListener('click', async () => {
    await runAdminAction(async () => {
      await api(`/api/movies/${movieId}/rating`, {
        method: 'PUT',
        body: JSON.stringify({ rating: Number(document.querySelector('#ratingInput').value) })
      })
      await selectLibraryMovie(movieId)
    }, 'Оценка сохранена')
  })

  document.querySelector('#saveNote')?.addEventListener('click', async () => {
    await runAdminAction(async () => {
      await api(`/api/movies/${movieId}/note`, {
        method: 'PUT',
        body: JSON.stringify({ note: document.querySelector('#noteInput').value })
      })
    }, 'Заметка сохранена')
  })
}

moviesEl.addEventListener('click', (event) => {
  const tile = event.target.closest('.movie-tile')
  if (!tile) return
  if (tile.dataset.mode === 'search') {
    selectSearchMovie(tile.dataset.id)
  } else {
    selectLibraryMovie(Number(tile.dataset.id))
  }
})

searchInput.addEventListener('input', () => {
  window.clearTimeout(state.searchTimer)
  state.searchTimer = window.setTimeout(() => {
    const query = searchInput.value.trim()
    if (query) searchRemote(query)
    else {
      state.searchResults = []
      renderMovies()
      if (state.library[0]) selectLibraryMovie(state.library[0].id)
    }
  }, 450)
})

statusFilter.addEventListener('change', () => loadLibrary())

document.querySelector('#tokenButton').addEventListener('click', () => {
  const token = prompt('ADMIN_TOKEN из .env', state.token)
  if (token !== null) {
    state.token = token.trim()
    localStorage.setItem('adminToken', state.token)
    updateTokenStatus()
    showToast(state.token ? 'Токен сохранён в браузере' : 'Токен очищен')
  }
})

document.querySelector('#addButton').addEventListener('click', () => movieDialog.showModal())
document.querySelector('#cancelMovie').addEventListener('click', () => movieDialog.close())

movieForm.addEventListener('submit', async (event) => {
  event.preventDefault()
  await runAdminAction(async () => {
    const data = Object.fromEntries(new FormData(movieForm))
    data.year = data.year ? Number(data.year) : null
    await api('/api/movies', { method: 'POST', body: JSON.stringify(data) })
    movieDialog.close()
    movieForm.reset()
    await loadLibrary()
  }, 'Фильм добавлен')
})

updateTokenStatus()
loadLibrary().catch((error) => {
  moviesEl.innerHTML = `<p class="error">Ошибка загрузки: ${escapeHtml(error.message)}</p>`
})
