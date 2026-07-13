# 🎓 TUT Event Management System

A web-based platform built by **TriTech Solutions** to fix how Tshwane University of Technology (TUT) runs its campus events — replacing flyers, WhatsApp groups, and Google Forms with a proper system. Organizers create and manage events; students discover, register, and check in with secure **QR-code eTickets**.

> 📚 Independent side project, started after graduating from TUT — Jun 2025 – Nov 2025

🔗 **Live Demo:** [mytutevents.vercel.app](https://mytutevents.vercel.app/)

---

## 📖 The Problem I Set Out to Solve

I built this right after finishing my final year, during recess. TUT — my own campus — was still running events the old way: paper forms, flyers, WhatsApp groups, and the occasional Google Form. There was no single place to see what was actually happening on campus that week, so most students simply missed events. Ticketing had no real structure, and organizers had no clean way to manage capacity or keep track of event photos afterward.

I brought the idea to two friends, we formed a team of three, and — since there were three of us — called ourselves **TriTech Solutions**. This project also became my way into backend development: I taught myself **Python and Flask** from scratch specifically to build it.

The result is a platform where organizers publish and manage real events with proper details, and students register and get a scannable **QR-code ticket** instead of relying on a forwarded flyer and hoping they remember.

---

## 🚀 Features

### 🔹 Admin / Organizer Features
- 🔐 **Secure Authentication:** Login with staff ID and password using Flask sessions and bcrypt hashing.
- 🗓️ **Event Management:** Create, update, and delete events with full details (title, date, time, venue, description).
- 🖼️ **Media Uploads:** Upload event posters and flyers.
- 📢 **Notifications:** Send updates to students via email (SMTP) and WhatsApp (WhatsApp API).
- 📊 **Organizer Dashboard:** Manage upcoming/past events, view analytics and attendance stats.

### 🔹 Student Features
- 🏠 **Dynamic Landing Page:** Event highlights and important information.
- 🔐 **Secure Login & Signup:** Encrypted passwords, session-based authentication.
- 🧭 **Event Exploration:** Browse current/upcoming/past events, event galleries, and organizers.
- 🎟️ **Event Registration:** Register online and receive a **QR-code ticket** for check-in.

### 🔹 Additional Features
- 🎨 **Modern UI:** Dark-themed interface with brand colors (dark blue, dark red, dark yellow).
- ⚡ **Interactive Design:** Smooth animations, hover effects, transitions.
- 📱 **Responsive Layout:** Desktop, tablet, and mobile.
- 🔎 **Search & Filter:** Quickly find events.
- 👤 **User Profiles:** Personalized dashboards for students and organizers.
- 🛡️ **Admin Security:** Only verified TUT organizers can post events.

---

## 🛠️ Tech Stack

| Layer | Technology |
|:------|:------------|
| **Frontend** | HTML, CSS, JavaScript |
| **Backend** | Python (Flask) |
| **Database** | PostgreSQL |
| **Hosting** | Vercel |
| **Notifications** | WhatsApp API, SMTP (Email) |
| **QR Code Generation** | `qrcode`, `pyqrcode` |
| **Version Control** | Git & GitHub |

---

## 👥 Developers — *TriTech Solutions*

- **Thabang Dikotope** — Team Lead & Backend Developer — identified the problem, proposed the solution, and led development
- **Pholosho Mashabela** — UI Developer
- **Bongani Mathe** — Database Developer

---

## 🤝 Contributing

We welcome contributions and ideas! Fork this repository, make your changes, and open a pull request.

---

## 📧 Contact

For inquiries or support, reach out to the **TriTech Solutions** team:
📩 tritechsolutions.co.za

---

⭐ *Developed with passion by students of Tshwane University of Technology.*
