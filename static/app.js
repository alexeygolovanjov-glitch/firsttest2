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

function bindDetailActions(movieId) {
  document.querySelector('#listSelect').addEventListener('change', async (event) => {
    await api(`/api/movies/${movieId}/list`, {
      method: 'PUT',
      body: JSON.stringify({ status: event.target.value })
    })
    await loadMovies()
  })

  document.querySelector('#saveRating').addEventListener('click', async () => {
    const rating = Number(document.querySelector('#ratingInput').value)
    await api(`/api/movies/${movieId}/rating`, {
      method: 'PUT',
      body: JSON.stringify({ rating })
    })
    await loadMovies()
  })

  document.querySelector('#saveNote').addEventListener('click', async () => {
    await api(`/api/movies/${movieId}/note`, {
      method: 'PUT',
      body: JSON.stringify({ note: document.querySelector('#noteInput').value })
    })
  })

  document.querySelector('#commentForm').addEventListener('submit', async (event) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await api(`/api/movies/${movieId}/comments`, {
      method: 'POST',
      body: JSON.stringify(Object.fromEntries(form))
    })
    await renderDetails()
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

document.querySelector('#tokenButton').addEventListener('click', () => {
  const token = prompt('ADMIN_TOKEN из .env', state.token)
  if (token !== null) {
    state.token = token.trim()
    localStorage.setItem('adminToken', state.token)
  }
})

document.querySelector('#addButton').addEventListener('click', () => movieDialog.showModal())
document.querySelector('#cancelMovie').addEventListener('click', () => movieDialog.close())

movieForm.addEventListener('submit', async (event) => {
  event.preventDefault()
  const data = Object.fromEntries(new FormData(movieForm))
  data.year = data.year ? Number(data.year) : null
  await api('/api/movies', { method: 'POST', body: JSON.stringify(data) })
  movieDialog.close()
  movieForm.reset()
  await loadMovies()
})

loadMovies().catch((error) => {
  moviesEl.innerHTML = `<p class="error">Ошибка загрузки: ${escapeHtml(error.message)}</p>`
})
