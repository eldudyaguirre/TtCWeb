document.addEventListener('DOMContentLoaded', function () {
    const groups = document.querySelectorAll('.portal-menu-group');
    const links = document.querySelectorAll('[data-menu-link]');

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

    groups.forEach(function (group) {
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
                event.preventDefault();
                clearSelection();
                item.classList.add('active');
                toggle.classList.add('active');
                group.classList.add('open');
                toggle.setAttribute('aria-expanded', 'true');
            });
        });
    });

    links.forEach(function (link) {
        link.addEventListener('click', function (event) {
            event.preventDefault();
            clearSelection();
            link.classList.add('active');
            groups.forEach(function (group) {
                group.classList.remove('open');
                group.querySelector('.portal-menu-toggle').setAttribute('aria-expanded', 'false');
            });
        });
    });
});
