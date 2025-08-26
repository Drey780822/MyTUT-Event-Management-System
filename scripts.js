let user = { id: 'S123456', name: 'John Doe', role: 'student' };
let events = [
  { id: 1, title: 'Career Fair', date: '2025-09-10', time: '10:00', venue: 'Main Hall', category: 'career', capacity: 100, registered: 50, attendees: [], description: 'Explore career opportunities', image: 'https://via.placeholder.com/300' },
  { id: 2, title: 'Soccer Tournament', date: '2025-09-15', time: '14:00', venue: 'Sports Field', category: 'sports', capacity: 200, registered: 150, attendees: [], description: 'Join the annual soccer event', image: 'https://via.placeholder.com/300' },
];

function updateUserInfo() {
  const userInfo = document.getElementById('user-info');
  const createEventLink = document.getElementById('create-event-link');
  if (userInfo) {
    userInfo.textContent = `Welcome, ${user.name} (${user.role})`;
  }
  if (createEventLink && isOrganizerOrAdmin()) {
    createEventLink.style.display = 'inline';
  }
}

function isOrganizerOrAdmin() {
  return user.role === 'organizer' || user.role === 'admin';
}

function renderEvents() {
  const eventGrid = document.getElementById('event-grid');
  if (!eventGrid) return;
  eventGrid.innerHTML = events.map(event => `
    <div class="event-card">
      <h3>${event.title}</h3>
      <p>Date: ${event.date}</p>
      <p>Category: ${event.category}</p>
      <p>Capacity: ${event.registered}/${event.capacity}</p>
      <a href="event-details.html?id=${event.id}">View Details</a>
    </div>
  `).join('');
}