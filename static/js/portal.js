document.addEventListener('DOMContentLoaded', function () {
    const groups = document.querySelectorAll('.portal-menu-group');
    const links = document.querySelectorAll('[data-menu-link]');
    const sidebar = document.querySelector('.portal-sidebar');
    const mobileToggle = document.querySelector('.portal-mobile-toggle');

    function clearSelection() {
        document.querySelectorAll('.portal-submenu-item.active').forEach(function (item) {
            item.classList.remove('active');
        });
        document.querySelectorAll('[data-menu-link].active').forEach(function (item) {
            item.classList.remove('active');
        });
        document.querySelectorAll('.portal-menu-toggle.active').forEach(function (item) {
            item.classList.remove('active');
        });
    }

    function closeMobileMenu() {
        if (!sidebar || !mobileToggle) return;
        sidebar.classList.remove('mobile-open');
        mobileToggle.setAttribute('aria-expanded', 'false');
        mobileToggle.setAttribute('aria-label', 'Abrir menú');
        const icon = mobileToggle.querySelector('i');
        if (icon) icon.className = 'fi fi-rr-menu-burger';
    }

    if (mobileToggle) {
        mobileToggle.addEventListener('click', function () {
            const open = sidebar.classList.toggle('mobile-open');
            mobileToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            mobileToggle.setAttribute('aria-label', open ? 'Cerrar menú' : 'Abrir menú');
            const icon = mobileToggle.querySelector('i');
            if (icon) {
                icon.className = open ? 'fi fi-rr-cross-small' : 'fi fi-rr-menu-burger';
            }
        });
    }

    groups.forEach(function (group) {
        const activeToggle = group.querySelector('.portal-menu-toggle.active');
        if (activeToggle) {
            group.classList.add('open');
            activeToggle.setAttribute('aria-expanded', 'true');
        }

        const toggle = group.querySelector('.portal-menu-toggle');
        const submenuItems = group.querySelectorAll('.portal-submenu-item');

        toggle.addEventListener('click', function () {
            const wasOpen = group.classList.contains('open');

            groups.forEach(function (otherGroup) {
                otherGroup.classList.remove('open');
                otherGroup.querySelector('.portal-menu-toggle').setAttribute('aria-expanded', 'false');
            });

            if (!wasOpen) {
                group.classList.add('open');
                toggle.setAttribute('aria-expanded', 'true');
            }
        });

        submenuItems.forEach(function (item) {
            item.addEventListener('click', function (event) {
                const href = item.getAttribute('href');

                if (href && href !== '#') {
                    clearSelection();
                    item.classList.add('active');
                    toggle.classList.add('active');
                    if (window.innerWidth <= 767) closeMobileMenu();
                    window.location.href = href;
                    return;
                }

                event.preventDefault();
                clearSelection();
                item.classList.add('active');
                toggle.classList.add('active');
                group.classList.add('open');
                toggle.setAttribute('aria-expanded', 'true');
                if (window.innerWidth <= 767) closeMobileMenu();
            });
        });
    });

    links.forEach(function (link) {
        link.addEventListener('click', function (event) {
            const href = link.getAttribute('href');

            if (href && href !== '#') {
                clearSelection();
                if (window.innerWidth <= 767) closeMobileMenu();
                return;
            }

            event.preventDefault();
            clearSelection();
            link.classList.add('active');
            groups.forEach(function (group) {
                group.classList.remove('open');
                group.querySelector('.portal-menu-toggle').setAttribute('aria-expanded', 'false');
            });
            if (window.innerWidth <= 767) closeMobileMenu();
        });
    });

    window.addEventListener('resize', function () {
        if (window.innerWidth > 767) closeMobileMenu();
    });
});