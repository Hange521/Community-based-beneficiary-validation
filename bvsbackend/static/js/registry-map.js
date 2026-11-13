const pointsElement = document.getElementById('registryMapData');
const mapElement = document.getElementById('registryMap');

if (pointsElement && mapElement && window.L) {
  const points = JSON.parse(pointsElement.textContent);
  const map = L.map(mapElement, { scrollWheelZoom: false });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map);

  const bounds = [];
  points.forEach((point) => {
    const position = [point.latitude, point.longitude];
    bounds.push(position);
    const popup = document.createElement('div');
    const record = document.createElement('strong');
    record.textContent = point.beneficiary_id;
    const community = document.createElement('div');
    community.textContent = `${point.purok}, ${point.barangay}`;
    popup.append(record, community);
    L.marker(position).addTo(map).bindPopup(popup);
  });

  if (bounds.length === 1) {
    map.setView(bounds[0], 15);
  } else {
    map.fitBounds(bounds, { padding: [24, 24], maxZoom: 15 });
  }
}