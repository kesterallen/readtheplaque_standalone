/*
 * Shared primary-image selection controller.
 * Items use data-image-item, buttons use data-set-primary, and badges use
 * data-primary-badge. onSelect may be asynchronous and returns false to reject.
 */
(function (global) {
  'use strict';

  function createImagePrimaryController(options) {
    options = options || {};
    var container = options.container;
    var itemSelector = options.itemSelector || '[data-image-item]';
    var buttonSelector = options.buttonSelector || '[data-set-primary]';
    var badgeSelector = options.badgeSelector || '[data-primary-badge]';
    var actionsSelector = options.actionsSelector || '[data-image-actions]';
    var onSelect = options.onSelect || function () {};
    var selectedItem = options.initialItem || null;

    if (!container) throw new Error('createImagePrimaryController requires a container');

    function getItems() {
      return Array.prototype.slice.call(container.querySelectorAll(itemSelector));
    }

    function render() {
      getItems().forEach(function (item) {
        var selected = item === selectedItem;
        var badge = item.querySelector(badgeSelector);
        var button = item.querySelector(buttonSelector);

        if (selected && !badge) {
          badge = document.createElement('span');
          badge.setAttribute('data-primary-badge', '');
          badge.className = options.badgeClass || 'image-primary-badge';
          badge.textContent = options.badgeText || 'Primary';
          var actions = item.querySelector(actionsSelector);
          item.insertBefore(badge, actions || null);
        } else if (!selected && badge) {
          badge.remove();
        }
        if (badge) badge.style.display = selected ? 'inline-block' : 'none';

        var image = item.querySelector('img');
        if (image && options.highlightImage) {
          image.style.borderColor = selected ? 'var(--amber)' : 'var(--border)';
          image.title = selected ? 'Primary image' : '';
        }

        if (button) {
          button.disabled = selected;
          button.textContent = selected
            ? (options.selectedButtonText || '★ Primary image')
            : (options.buttonText || '★ Set as primary');
          if (options.hideSelectedButton) button.style.display = selected ? 'none' : '';
        }
        if (options.selectedClass) item.classList.toggle(options.selectedClass, selected);
      });
    }

    function select(item) {
      if (!item || !container.contains(item) || item === selectedItem) return Promise.resolve(false);
      return Promise.resolve(onSelect(item)).then(function (accepted) {
        if (accepted === false) return false;
        selectedItem = item;
        render();
        return true;
      });
    }

    container.addEventListener('click', function (event) {
      var button = event.target && event.target.closest
        ? event.target.closest(buttonSelector) : null;
      if (!button || !container.contains(button)) return;
      event.preventDefault();
      select(button.closest(itemSelector)).catch(function (error) {
        console.error('Could not set primary image:', error);
      });
    });

    function refresh(primaryItem) {
      if (arguments.length) selectedItem = primaryItem || null;
      if (selectedItem && !container.contains(selectedItem)) selectedItem = null;
      render();
    }

    render();
    return {
      select: select,
      refresh: refresh,
      getPrimaryItem: function () { return selectedItem; },
      getPrimaryIndex: function () { return getItems().indexOf(selectedItem); }
    };
  }

  global.createImagePrimaryController = createImagePrimaryController;
})(window);
