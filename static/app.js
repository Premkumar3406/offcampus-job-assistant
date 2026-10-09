
const searchForm = document.getElementById("searchForm");
const roleInput = document.getElementById("role");
const locationInput = document.getElementById("location");
const jobResults = document.getElementById("jobResults");
const applicationResults =
    document.getElementById("applicationResults");
const message = document.getElementById("message");

let currentJobs = [];

// Escape text before placing API data into HTML.
function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[char]);
}

function getSearchValues() {
    return {
        q: roleInput.value.trim() || "software developer fresher",
        location: locationInput.value.trim() || "India"
    };
}

function updatePortalLinks(portals) {
    document.getElementById("linkedinLink").href =
        portals.linkedin;

    document.getElementById("naukriLink").href =
        portals.naukri;
}

async function searchJobs(event) {
    if (event) event.preventDefault();

    const button = document.getElementById("searchButton");
    button.disabled = true;
    button.textContent = "Searching...";
    message.textContent = "Looking for recent job listings...";
    jobResults.innerHTML = "";

    const params = new URLSearchParams(getSearchValues());

    try {
        const response = await fetch(`/api/jobs?${params}`);
        const data = await response.json();

        currentJobs = data.jobs || [];
        updatePortalLinks(data.portals);

        document.getElementById("jobCount").textContent =
            currentJobs.length;

        if (data.error) {
            message.textContent = data.error;
        } else {
            message.textContent =
                `${data.count} matching listings found in the ` +
                `available public feed. ${data.message || ""}`;
        }

        renderJobs();
    } catch (error) {
        message.textContent =
            "Unable to connect to the server. Check that Flask is running.";
    } finally {
        button.disabled = false;
        button.textContent = "Search recent jobs";
    }
}

function renderJobs() {
    if (currentJobs.length === 0) {
        jobResults.innerHTML = `
            <div class="empty-state">
                No matching jobs were found in this public feed.
                Try a broader keyword, or use the LinkedIn and Naukri
                search links above. This does not mean there are no
                jobs open on those portals.
            </div>`;
        return;
    }

    jobResults.innerHTML = currentJobs.map((job, index) => {
        const tags = (job.tags || []).slice(0, 5)
            .map(tag => `<span class="tag">${escapeHTML(tag)}</span>`)
            .join("");

        return `
            <article class="job-card">
                <h3>${escapeHTML(job.title)}</h3>
                <div class="company">${escapeHTML(job.company)}</div>

                <div class="job-meta">
                    📍 ${escapeHTML(job.location)}<br>
                    🕒 Posted: ${escapeHTML(job.posted_text)}<br>
                    🌐 Source: ${escapeHTML(job.source)}
                </div>

                <div class="tags">${tags}</div>

                <div class="job-actions">
                    <a class="apply-link"
                       href="${escapeHTML(job.url)}"
                       target="_blank"
                       rel="noopener noreferrer">
                        View application ↗
                    </a>
                    <button class="secondary"
                            data-save-index="${index}">
                        Save job
                    </button>
                </div>
            </article>`;
    }).join("");

    jobResults.querySelectorAll("[data-save-index]")
        .forEach(button => {
            button.addEventListener("click", async () => {
                const job = currentJobs[
                    Number(button.dataset.saveIndex)
                ];
                await saveJob(job, button);
            });
        });
}

async function saveJob(job, button) {
    button.disabled = true;

    try {
        const response = await fetch("/api/applications", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(job)
        });

        const data = await response.json();

        if (!response.ok) {
            alert(data.error || "Could not save this job.");
            return;
        }

        await loadApplications();
        button.textContent = "Saved ✓";
    } catch (error) {
        alert("Could not reach the server.");
    } finally {
        button.disabled = false;
    }
}

async function loadApplications() {
    try {
        const response = await fetch("/api/applications");
        if (!response.ok) throw new Error("Request failed");

        const applications = await response.json();

        document.getElementById("savedCount").textContent =
            applications.length;

        if (applications.length === 0) {
            applicationResults.innerHTML = `
                <div class="empty-state">
                    Your tracker is empty. Save a job to get started.
                </div>`;
            return;
        }

        const statuses = [
            "Saved", "Ready to Apply", "Applied",
            "Interview", "Rejected", "Closed"
        ];

        applicationResults.innerHTML = applications.map(app => `
            <div class="tracker-item">
                <div>
                    <strong>${escapeHTML(app.title)}</strong>
                    <div class="job-meta">
                        ${escapeHTML(app.company)} ·
                        ${escapeHTML(app.location)}
                    </div>
                    <a href="${escapeHTML(app.url)}"
                       target="_blank"
                       rel="noopener noreferrer">
                        Open job ↗
                    </a>
                </div>

                <label>
                    <span class="job-meta">Status</span><br>
                    <select data-status-id="${app.id}">
                        ${statuses.map(status => `
                            <option value="${status}"
                                ${status === app.status ? "selected" : ""}>
                                ${status}
                            </option>`).join("")}
                    </select>
                </label>
            </div>
        `).join("");

        applicationResults.querySelectorAll("[data-status-id]")
            .forEach(select => {
                select.addEventListener("change", async () => {
                    const previousValue = select.dataset.previous ||
                        applications.find(a =>
                            String(a.id) === select.dataset.statusId
                        )?.status || "Saved";

                    try {
                        const response = await fetch(
                            `/api/applications/${select.dataset.statusId}`,
                            {
                                method: "PATCH",
                                headers: {
                                    "Content-Type": "application/json"
                                },
                                body: JSON.stringify({
                                    status: select.value
                                })
                            }
                        );

                        if (!response.ok) {
                            throw new Error("Update failed");
                        }

                        select.dataset.previous = select.value;
                    } catch (error) {
                        select.value = previousValue;
                        alert("Could not update application status.");
                    }
                });
            });
    } catch (error) {
        applicationResults.innerHTML = `
            <div class="empty-state">
                Could not load the application tracker.
            </div>`;
    }
}

searchForm.addEventListener("submit", searchJobs);

document.addEventListener("DOMContentLoaded", async () => {
    await loadApplications();
    await searchJobs();
});
