document.addEventListener('DOMContentLoaded', () => {
    // Dark/Light Mode Toggle
    const themeToggle = document.querySelector('.theme-toggle');
    const body = document.body;
    const themeIcon = document.querySelector('.theme-icon');

    // Load saved theme from localStorage
    if (localStorage.getItem('theme') === 'light') {
        body.classList.add('light-mode');
        themeIcon.textContent = '☀️';
    } else {
        themeIcon.textContent = '🌙';
    }

    themeToggle.addEventListener('click', () => {
        body.classList.toggle('light-mode');
        const isLightMode = body.classList.contains('light-mode');
        themeIcon.textContent = isLightMode ? '☀️' : '🌙';
        localStorage.setItem('theme', isLightMode ? 'light' : 'dark');
    });

    // Filter Reset Button
    const resetButton = document.querySelector('.reset-button');
    if (resetButton) {
        resetButton.addEventListener('click', () => {
            const form = document.querySelector('.search-filter-bar');
            form.reset();
            form.submit();
        });
    }

    // Loading Animation
    const form = document.querySelector('.search-filter-bar');
    const dealsGrid = document.querySelector('.deals-grid');
    const paginationLinks = document.querySelectorAll('.pagination a');

    if (form) {
        form.addEventListener('submit', () => {
            dealsGrid.classList.add('loading');
        });
    }

    paginationLinks.forEach(link => {
        link.addEventListener('click', () => {
            dealsGrid.classList.add('loading');
        });
    });

    // Favorite Button Logic (existing)
    document.querySelectorAll('.btn-favorite').forEach(button => {
        button.addEventListener('click', () => {
            const product = button.getAttribute('data-product');
            let favorites = document.cookie
                .split('; ')
                .find(row => row.startsWith('favorites='));
            favorites = favorites ? JSON.parse(decodeURIComponent(favorites.split('=')[1])) : [];

            if (favorites.includes(product)) {
                favorites = favorites.filter(fav => fav !== product);
                button.textContent = '☆';
                button.closest('.deal-card').dataset.favorite = 'false';
            } else {
                favorites.push(product);
                button.textContent = '★';
                button.closest('.deal-card').dataset.favorite = 'true';
            }

            document.cookie = `favorites=${encodeURIComponent(JSON.stringify(favorites))}; path=/; max-age=3600`;
        });
    });
});
