const locationMapElement = document.getElementById('registrationLocationMap');
const latitudeInput = document.getElementById('id_registration_latitude');
const longitudeInput = document.getElementById('id_registration_longitude');
const locationStatus = document.getElementById('registrationLocationStatus');
const currentLocationButton = document.querySelector('.registration-location-button');

if (locationMapElement && latitudeInput && longitudeInput && window.L) {
  const defaultCenter = [8.947, 125.54];
  const map = L.map(locationMapElement).setView(defaultCenter, 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map);

  let marker;
  const setPin = (latitude, longitude) => {
    const position = [latitude, longitude];
    latitudeInput.value = latitude.toFixed(6);
    longitudeInput.value = longitude.toFixed(6);
    if (marker) marker.setLatLng(position);
    else marker = L.marker(position).addTo(map);
    locationStatus.textContent = `Selected location: ${latitudeInput.value}, ${longitudeInput.value}`;
  };

  map.on('click', (event) => setPin(event.latlng.lat, event.latlng.lng));
  const disclosure = locationMapElement.closest('details');
  disclosure?.addEventListener('toggle', () => {
    if (disclosure.open) requestAnimationFrame(() => map.invalidateSize());
  });

  if (latitudeInput.value && longitudeInput.value) {
    const savedLocation = [Number(latitudeInput.value), Number(longitudeInput.value)];
    map.setView(savedLocation, 15);
    setPin(...savedLocation);
  }

  currentLocationButton?.addEventListener('click', () => {
    if (!navigator.geolocation) {
      locationStatus.textContent = 'Location is not available in this browser. You can select a point on the map.';
      return;
    }
    locationStatus.textContent = 'Requesting location permission…';
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setPin(coords.latitude, coords.longitude);
        map.setView([coords.latitude, coords.longitude], 15);
      },
      () => { locationStatus.textContent = 'Location was not shared. You can select a point on the map.'; },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    );
  });
}