document.addEventListener('DOMContentLoaded', () => {
    // --- Получаем все нужные элементы ---
    const form = document.getElementById('explain-form');
    const topicInput = document.getElementById('topic-input');
    const levelSelect = document.getElementById('level-select');
    const analogyGroup = document.getElementById('analogy-group');
    const analogyInput = document.getElementById('analogy-input');
    const submitButton = document.getElementById('submit-button');
    const loadingIndicator = document.getElementById('loading-indicator');
    const resultArea = document.getElementById('result-area');
    const explanationOutput = document.getElementById('explanation-output');
    const errorArea = document.getElementById('error-area');
    const errorMessage = document.getElementById('error-message');
    const explanationLinkContainer = document.getElementById('explanation-link-container');
    const explanationLink = document.getElementById('explanation-link');
    const searchInput = document.getElementById('search-input');
    const searchResultsContainer = document.getElementById('search-results');

    // --- Инициализация markdown-it ---
    const md = window.markdownit({
        html: false, linkify: true, typographer: true,
        highlight: function (str, lang) {
            if (lang && hljs.getLanguage(lang)) {
                try { return '<pre class="hljs"><code>' + hljs.highlight(str, { language: lang, ignoreIllegals: true }).value + '</code></pre>'; } catch (__) {}
            } return '<pre class="hljs"><code>' + md.utils.escapeHtml(str) + '</code></pre>'; }
    });

    // --- Логика формы объяснений ---
    levelSelect?.addEventListener('change', () => {
        if (levelSelect.value === 'custom_analogy') {
            analogyGroup.style.display = 'block';
            analogyInput.required = true;
        } else {
            analogyGroup.style.display = 'none';
            analogyInput.required = false;
            analogyInput.value = '';
        }
    });

    form?.addEventListener('submit', async (event) => {
        event.preventDefault();
        // ... (Сброс состояний UI как раньше) ...
        loadingIndicator.style.display = 'block';
        resultArea.style.display = 'none';
        errorArea.style.display = 'none';
        explanationLinkContainer.style.display = 'none';
        submitButton.disabled = true;
        submitButton.textContent = 'Думаем...';
        explanationOutput.innerHTML = '';

        const formData = {
            topic: topicInput.value.trim(),
            level: levelSelect.value,
            analogy: levelSelect.value === 'custom_analogy' ? analogyInput.value.trim() : null
        };

        // ... (Валидация как раньше) ...
        if (!formData.topic || (formData.level === 'custom_analogy' && !formData.analogy)) {
             showError(formData.level === 'custom_analogy' ? "Введите аналогию." : "Введите тему.");
             resetButton(); return;
         }

        try {
            const response = await fetch('/api/explain', { /* ... как раньше ... */
                 method: 'POST', headers: {'Content-Type': 'application/json','Accept': 'application/json'},
                 body: JSON.stringify(formData)
            });

            loadingIndicator.style.display = 'none';
            resetButton();

            if (!response.ok) { /* ... Обработка ошибок ответа ... */
                 let errorDetail = `Ошибка ${response.status}. Попробуйте позже.`;
                 try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail;} catch (e) {}
                 showError(errorDetail); return;
            }

            const data = await response.json();

            if (data.explanation) {
                // Проверяем, не является ли ответ сообщением об ошибке (если slug == null)
                if (!data.slug) {
                    showError("Не удалось сгенерировать качественное объяснение. Ответ: " + data.explanation);
                } else {
                    const htmlContent = md.render(data.explanation);
                    explanationOutput.innerHTML = htmlContent;
                    addCopyButtons(explanationOutput); // Добавляем кнопки копирования
                    resultArea.style.display = 'block';
                    errorArea.style.display = 'none'; // Прячем ошибку при успехе

                    const linkUrl = `/explanation/${data.slug}`;
                    explanationLink.href = linkUrl;
                    explanationLinkContainer.style.display = 'block';
                }
            } else {
                 showError("Получен пустой ответ от сервера.");
            }

        } catch (error) { /* ... Обработка ошибок сети ... */
             console.error("Fetch error:", error);
             loadingIndicator.style.display = 'none';
             showError(`Произошла ошибка сети или сервера: ${error.message}.`);
             resetButton();
        }
    });

    function showError(message) { /* ... как раньше ... */
        errorMessage.textContent = message;
        errorArea.style.display = 'block';
        resultArea.style.display = 'none';
        loadingIndicator.style.display = 'none';
        explanationLinkContainer.style.display = 'none';
    }
    function resetButton() { /* ... как раньше ... */
        if(submitButton) {
            submitButton.disabled = false;
            submitButton.textContent = 'Объяснить!';
        }
    }
    function addCopyButtons(container) { /* ... как раньше ... */
        const codeBlocks = container.querySelectorAll('pre code');
        codeBlocks.forEach((codeBlock) => {
             const preElement = codeBlock.parentNode;
             if (preElement.querySelector('.copy-button')) return;
            const button = document.createElement('button');
            button.className = 'copy-button'; button.textContent = 'Копировать'; button.setAttribute('aria-label', 'Копировать код');
            button.addEventListener('click', async () => { /* ... обработчик копирования ... */
                try {
                    await navigator.clipboard.writeText(codeBlock.innerText);
                    button.textContent = 'Скопировано!'; button.disabled = true;
                    setTimeout(() => { button.textContent = 'Копировать'; button.disabled = false; }, 2000);
                } catch (err) { console.error('Ошибка копирования:', err); button.textContent = 'Ошибка'; setTimeout(() => { button.textContent = 'Копировать'; }, 2000); }
            });
             preElement.style.position = 'relative';
            preElement.appendChild(button);
        });
    }


    // --- Логика Поиска ---
    let searchTimeout;

    searchInput?.addEventListener('input', () => {
        clearTimeout(searchTimeout); // Отменяем предыдущий таймаут
        const query = searchInput.value.trim();

        if (query.length < 3) {
            searchResultsContainer.style.display = 'none'; // Скрываем результаты если запрос короткий
            searchResultsContainer.innerHTML = '';
            return;
        }

        // Запускаем поиск с задержкой (debouncing)
        searchTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
                if (!response.ok) {
                    console.error("Search API error:", response.statusText);
                    searchResultsContainer.style.display = 'none';
                    return;
                }
                const data = await response.json();
                displaySearchResults(data.results);
            } catch (error) {
                console.error("Search fetch error:", error);
                searchResultsContainer.style.display = 'none';
            }
        }, 300); // Задержка 300 мс
    });

    // Скрываем результаты поиска при клике вне поля и результатов
    document.addEventListener('click', (event) => {
         if (!searchInput?.contains(event.target) && !searchResultsContainer?.contains(event.target)) {
              searchResultsContainer.style.display = 'none';
          }
     });
     // Также скрываем при потере фокуса с инпута (но с задержкой, чтобы успеть кликнуть по ссылке)
     searchInput?.addEventListener('blur', () => {
         setTimeout(() => {
              if (!searchResultsContainer.matches(':hover')) { // Не скрывать, если мышь над результатами
                 searchResultsContainer.style.display = 'none';
             }
         }, 150); // Небольшая задержка
     });
     // Показываем при фокусе, если есть текст
     searchInput?.addEventListener('focus', () => {
         if (searchInput.value.trim().length >= 3 && searchResultsContainer.innerHTML !== '') {
              searchResultsContainer.style.display = 'block';
          }
     });


    function displaySearchResults(results) {
        searchResultsContainer.innerHTML = ''; // Очищаем предыдущие результаты
        if (results.length === 0) {
            searchResultsContainer.innerHTML = '<div class="no-results">Ничего не найдено</div>';
        } else {
            results.forEach(item => {
                const link = document.createElement('a');
                link.href = `/explanation/${item.slug}`;
                link.textContent = item.topic;
                // Можно добавить title с полным текстом темы
                link.title = item.topic;
                searchResultsContainer.appendChild(link);
            });
        }
        searchResultsContainer.style.display = 'block'; // Показываем контейнер
    }

     // --- Рендеринг Markdown на странице объяснения (если мы на ней) ---
     const rawMarkdownEl = document.getElementById('raw-markdown');
     const explanationContentEl = document.getElementById('explanation-content');
     if (rawMarkdownEl && explanationContentEl) {
          const markdownText = rawMarkdownEl.textContent;
         explanationContentEl.innerHTML = md.render(markdownText);
          addCopyButtons(explanationContentEl);
      }

});