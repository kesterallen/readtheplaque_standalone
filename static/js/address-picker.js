/* Shared address search and MapLibre coordinate picker.
 * Pages provide the map container and coordinate inputs, then use the returned
 * setCoords() method when another feature (such as photo GPS) supplies a point.
 */
(function(global) {
  'use strict';

  function initAddressPicker(options) {
    options = options || {};

    var map = makeMap(options.mapId, {
      center: options.initialCoords
        ? [options.initialCoords.lng, options.initialCoords.lat]
        : (options.defaultCenter || [0, 20]),
      zoom: options.initialCoords ? (options.initialZoom || 10) : (options.defaultZoom || 0)
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-right');

    var latitudeInput = document.getElementById(options.latitudeId || 'latitude');
    var longitudeInput = document.getElementById(options.longitudeId || 'longitude');
    var addressInput = document.getElementById(options.addressId || 'addressSearch');
    var resultsElement = document.getElementById(options.resultsId || 'addressResults');
    var marker = null;
    var searchTimer = null;
    var searchController = null;

    function setCoords(lat, lng, moveMap) {
      lat = Number(lat);
      lng = Number(lng);

      if (!Number.isFinite(lat) || !Number.isFinite(lng)
          || Math.abs(lat) > 90 || Math.abs(lng) > 180) return false;

      latitudeInput.value = lat.toFixed(6);
      longitudeInput.value = lng.toFixed(6);

      if (!marker) {
        marker = new maplibregl.Marker({ color: '#d9534f', draggable: true })
          .setLngLat([lng, lat])
          .addTo(map);
        marker.on('dragend', function() {
          var point = marker.getLngLat();
          setCoords(point.lat, point.lng, false);
        });
      } else {
        marker.setLngLat([lng, lat]);
      }

      if (moveMap) {
        map.flyTo({
          center: [lng, lat],
          zoom: Math.max(map.getZoom(), options.selectionZoom || 12)
        });
      }
      return true;
    }

    map.on('click', function(event) {
      setCoords(event.lngLat.lat, event.lngLat.lng, false);
    });

    if (options.initialCoords) {
      setCoords(options.initialCoords.lat, options.initialCoords.lng, false);
    }

    [latitudeInput, longitudeInput].forEach(function(input) {
      input.addEventListener('change', function() {
        var lat = parseFloat(latitudeInput.value);
        var lng = parseFloat(longitudeInput.value);
        if (!isNaN(lat) && !isNaN(lng)) setCoords(lat, lng, true);
      });
    });

    function hideResults() {
      resultsElement.innerHTML = '';
      resultsElement.style.display = 'none';
    }

    async function searchAddress(query) {
      if (searchController) searchController.abort();
      searchController = new AbortController();

      try {
        var params = new URLSearchParams({
          q: query,
          format: 'jsonv2',
          limit: '5',
          addressdetails: '1',
          email: 'info@readtheplaque.com'
        });
        var response = await fetch(
          'https://nominatim.openstreetmap.org/search?' + params.toString(),
          {
            signal: searchController.signal,
            headers: {
              'Accept': 'application/json',
              'Referer': 'https://readtheplaque.com'
            }
          }
        );

        if (!response.ok) throw new Error('Nominatim request failed');
        var results = await response.json();
        hideResults();

        results.forEach(function(result) {
          var item = document.createElement('button');
          item.type = 'button';
          item.className = 'address-result';
          item.textContent = result.display_name;
          item.setAttribute('role', 'option');
          item.addEventListener('click', function() {
            if (setCoords(parseFloat(result.lat), parseFloat(result.lon), true)) {
              addressInput.value = result.display_name;
              hideResults();
            }
          });
          resultsElement.appendChild(item);
        });

        resultsElement.style.display = results.length ? 'block' : 'none';
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('Address search failed:', error);
          hideResults();
        }
      }
    }

    addressInput.addEventListener('input', function() {
      clearTimeout(searchTimer);
      var query = addressInput.value.trim();
      hideResults();
      if (query.length < 3) return;
      searchTimer = setTimeout(function() {
        searchAddress(query);
      }, 300);
    });

    document.addEventListener('click', function(event) {
      if (!addressInput.contains(event.target) && !resultsElement.contains(event.target)) {
        resultsElement.style.display = 'none';
      }
    });

    return { map: map, setCoords: setCoords };
  }

  global.initAddressPicker = initAddressPicker;
})(window);
