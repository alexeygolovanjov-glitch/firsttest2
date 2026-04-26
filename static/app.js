const state = {
  movies: [],
  selectedId: null,
  token: localStorage.getItem('adminToken') || ''
}

const moviesEl = document.querySelector('#movies')
const detailsEl = document.querySelector('#details')
const searchInput = document.querySelector('#searchInput')
const statusFilter = document.querySelector('#statusFilter')
const movieDialog = document.querySelector('#movieDialog')
const movieForm = document.querySelector('#movieForm')
const tokenStatus = document.querySelector('#tokenStatus')
const toast = document.querySelector('#toast')
const internetSearchButton = document.querySelector('#internetSearchButton')
const internetResults = document.querySelector('#internetResults')

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

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]
  })
}

async function loadMovies() {
  const params = new URLSearchParams()
  if (searchInput.value.trim()) params.set('query', searchInput.value.trim())
  params.set('status', statusFilter.value)
  state.movies = await api(`/api/movies?${params.toString()}`)
  renderMovies()
  if (state.selectedId) {
    const exists = state.movies.some((movie) => movie.id === state.selectedId)
    if (!exists) state.selectedId = state.movies[0]?.id || null
  } else {
    state.selectedId = state.movies[0]?.id || null
  }
  renderDetails()
}

function renderMovies() {
  moviesEl.innerHTML = state.movies
    .map((movie) => {
      const poster = movie.poster_url || '/assets/poster-placeholder.svg'
      return `
        <button class="movie-tile ${movie.id === state.selectedId ? 'active' : ''}" data-id="${movie.id}">
          <img src="${escapeHtml(poster)}" alt="" loading="lazy" />
          <span>${escapeHtml(movie.title)}</span>
          <small>${escapeHtml(movie.year || 'Без года')} · ${escapeHtml(statusLabels[movie.list_status] || 'Без списка')}</small>
        </button>
      `
    })
    .join('')
}

function renderInternetResults(results) {
  if (!results.length) {
    internetResults.hidden = false
    internetResults.innerHTML = '<p>В Кинопоиске ничего не найдено.</p>'
    return
  }

  internetResults.hidden = false
  internetResults.innerHTML = `
    <div class="internet-results-head">
      <strong>Найдено в Кинопоиске</strong>
      <button id="closeInternetResults" type="button">Скрыть</button>
    </div>
    <div class="internet-list">
      ${results
        .map(
          (movie) => `
            <article>
              <img src="${escapeHtml(movie.poster_url || '/assets/poster-placeholder.svg')}" alt="" />
              <div>
                <strong>${escapeHtml(movie.title)}</strong>
                <small>${escapeHtml(movie.year || 'Без года')} ${movie.genre ? `· ${escapeHtml(movie.genre)}` : ''}</small>
              </div>
              <button class="import-kinopoisk" data-kp-id="${escapeHtml(movie.kp_id)}" type="button">Импорт</button>
            </article>
          `
        )
        .join('')}
    </div>
  `
}

async function renderDetails() {
  if (!state.selectedId) {
    detailsEl.innerHTML = `
      <div class="empty-state">
        <span>Пока пусто</span>
        <p>Добавь первый фильм с легальным embed URL или ссылкой на источник.</p>
      </div>
    `
    return
  }

  const movie = await api(`/api/movies/${state.selectedId}`)
  const player = movie.player_url
    ? `<iframe src="${escapeHtml(movie.player_url)}" title="${escapeHtml(movie.title)}" allowfullscreen></iframe>`
    : `<div class="no-player">Плеер не указан</div>`

  detailsEl.innerHTML = `
    <div class="player">${player}</div>
    <div class="detail-body">
      <p class="eyebrow">${escapeHtml(movie.genre || 'Фильм')}</p>
      <h2>${escapeHtml(movie.title)}</h2>
      <p class="meta">${escapeHtml(movie.year || 'Без года')} ${movie.rating ? `· ${movie.rating}/10` : ''}</p>
      <p>${escapeHtml(movie.description || 'Описание пока не добавлено.')}</p>
      ${movie.source_url ? `<a class="source-link" href="${escapeHtml(movie.source_url)}" target="_blank" rel="noreferrer">Источник</a>` : ''}

      <section class="player-tools">
        <div>
          <h3>Плееры</h3>
          <p>${movie.kinopoisk_id ? `Кинопоиск ID: ${escapeHtml(movie.kinopoisk_id)}` : 'Для автопоиска нужен импорт из Кинопоиска.'}</p>
        </div>
        <button id="loadPlayers" type="button" ${movie.kinopoisk_id ? '' : 'disabled'}>Найти плееры</button>
      </section>
      <div id="playerChoices" class="player-choices"></div>

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

      <section class="comments">
        <h3>Комментарии</h3>
        <form id="commentForm">
          <input name="author" placeholder="Имя" value="Я" />
          <textarea name="content" rows="3" placeholder="Комментарий" required></textarea>
          <button>Добавить</button>
        </form>
        <div class="comment-list">
          ${(movie.comments || [])
            .map((comment) => `<article><strong>${escapeHtml(comment.author)}</strong><p>${escapeHtml(comment.content)}</p></article>`)
            .join('')}
        </div>
      </section>
    </div>
  `

  bindDetailActions(movie.id)
}

function renderProviderDiagnostics(providers = []) {
  if (!providers.length) return ''
  return `
    <div class="provider-diagnostics">
      ${providers
        .map((provider) => {
          const status = provider.ok ? `${provider.count} найдено` : provider.error || 'ошибка'
          const stateClass = provider.ok && provider.count > 0 ? 'ok' : 'warn'
          return `
            <span class="${stateClass}">
              ${escapeHtml(provider.name)}: ${escapeHtml(status)}
            </span>
          `
        })
        .join('')}
    </div>
  `
}

function renderPlayerChoices(payload) {
  const container = document.querySelector('#playerChoices')
  const players = Array.isArray(payload) ? payload : payload.players || []
  const diagnostics = Array.isArray(payload) ? '' : renderProviderDiagnostics(payload.providers || [])

  if (!players.length) {
    container.innerHTML = `${diagnostics}<p class="muted">Плееры не найдены для этого фильма.</p>`
    return
  }

  container.innerHTML = `
    ${diagnostics}
    ${players
      .map(
        (player) => `
          <article>
            <div>
              <strong>${escapeHtml(player.name || player.translate || 'Плеер')}</strong>
              <small>${escapeHtml([player.source, player.quality].filter(Boolean).join(' · '))}</small>
            </div>
            <button class="select-player" data-iframe="${escapeHtml(player.iframe)}" type="button">Выбрать</button>
          </article>
        `
      )
      .join('')}
  `
}

function bindDetailActions(movieId) {
  document.querySelector('#loadPlayers').addEventListener('click', async (event) => {
    const button = event.currentTarget
    try {
      button.disabled = true
      button.textContent = 'Ищу...'
      const players = await api(`/api/movies/${movieId}/players`)
      renderPlayerChoices(players)
    } catch (error) {
      showToast('Не удалось получить плееры', 'error')
      console.error(error)
    } finally {
      button.disabled = false
      button.textContent = 'Найти плееры'
    }
  })

  document.querySelector('#playerChoices').addEventListener('click', async (event) => {
    const button = event.target.closest('.select-player')
    if (!button) return

    await runAdminAction(async () => {
      await api(`/api/movies/${movieId}/player`, {
        method: 'PUT',
        body: JSON.stringify({ player_url: button.dataset.iframe })
      })
      await renderDetails()
    }, 'Плеер выбран')
  })

  document.querySelector('#listSelect').addEventListener('change', async (event) => {
    await runAdminAction(async () => {
      await api(`/api/movies/${movieId}/list`, {
        method: 'PUT',
        body: JSON.stringify({ status: event.target.value })
      })
      await loadMovies()
    }, 'Статус сохранен')
  })

  document.querySelector('#saveRating').addEventListener('click', async () => {
    await runAdminAction(async () => {
      const rating = Number(document.querySelector('#ratingInput').value)
      await api(`/api/movies/${movieId}/rating`, {
        method: 'PUT',
        body: JSON.stringify({ rating })
      })
      await loadMovies()
    }, 'Оценка сохранена')
  })

  document.querySelector('#saveNote').addEventListener('click', async () => {
    await runAdminAction(async () => {
      await api(`/api/movies/${movieId}/note`, {
        method: 'PUT',
        body: JSON.stringify({ note: document.querySelector('#noteInput').value })
      })
    }, 'Заметка сохранена')
  })

  document.querySelector('#commentForm').addEventListener('submit', async (event) => {
    event.preventDefault()
    await runAdminAction(async () => {
      const form = new FormData(event.currentTarget)
      await api(`/api/movies/${movieId}/comments`, {
        method: 'POST',
        body: JSON.stringify(Object.fromEntries(form))
      })
      await renderDetails()
    }, 'Комментарий добавлен')
  })
}

moviesEl.addEventListener('click', (event) => {
  const tile = event.target.closest('.movie-tile')
  if (!tile) return
  state.selectedId = Number(tile.dataset.id)
  renderMovies()
  renderDetails()
})

searchInput.addEventListener('input', () => loadMovies())
statusFilter.addEventListener('change', () => loadMovies())

internetSearchButton.addEventListener('click', async () => {
  const query = searchInput.value.trim()
  if (!query) {
    showToast('Введите название для поиска', 'error')
    return
  }

  try {
    internetSearchButton.disabled = true
    internetSearchButton.textContent = 'Ищу...'
    const results = await api(`/api/search/kinopoisk?query=${encodeURIComponent(query)}`)
    renderInternetResults(results)
  } catch (error) {
    const message = String(error.message || '')
    if (message.includes('KINOPOISK_API_KEY')) {
      showToast('На сервере не задан KINOPOISK_API_KEY', 'error')
      return
    }
    showToast('Кинопоиск сейчас не ответил', 'error')
    console.error(error)
  } finally {
    internetSearchButton.disabled = false
    internetSearchButton.textContent = 'Кинопоиск'
  }
})

internetResults.addEventListener('click', async (event) => {
  if (event.target.id === 'closeInternetResults') {
    internetResults.hidden = true
    internetResults.innerHTML = ''
    return
  }

  const button = event.target.closest('.import-kinopoisk')
  if (!button) return

  await runAdminAction(async () => {
    const movie = await api(`/api/import/kinopoisk/${button.dataset.kpId}`, { method: 'POST' })
    state.selectedId = movie.id
    await loadMovies()
    internetResults.hidden = true
    internetResults.innerHTML = ''
  }, 'Фильм импортирован')
})

document.querySelector('#tokenButton').addEventListener('click', () => {
  const token = prompt('ADMIN_TOKEN из .env', state.token)
  if (token !== null) {
    state.token = token.trim()
    localStorage.setItem('adminToken', state.token)
    updateTokenStatus()
    showToast(state.token ? 'Токен сохранен в браузере' : 'Токен очищен')
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
    await loadMovies()
  }, 'Фильм добавлен')
})

updateTokenStatus()
loadMovies().catch((error) => {
  moviesEl.innerHTML = `<p class="error">Ошибка загрузки: ${escapeHtml(error.message)}</p>`
})
