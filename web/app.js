document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const extractForm = document.getElementById("extract-form");
    const channelInput = document.getElementById("channel-input");
    const periodSelect = document.getElementById("period-select");
    const customDateContainer = document.getElementById("custom-date-container");
    const startDateInput = document.getElementById("start-date");
    const endDateInput = document.getElementById("end-date");
    const extractBtn = document.getElementById("extract-btn");
    const btnSpinner = document.getElementById("btn-spinner");
    
    const progressContainer = document.getElementById("progress-container");
    const progressBar = document.getElementById("progress-bar");
    const progressStatusText = document.getElementById("progress-status-text");
    const progressPercentage = document.getElementById("progress-percentage");
    const logBox = document.getElementById("log-box");

    const channelsList = document.getElementById("channels-list");
    const refreshChannelsBtn = document.getElementById("refresh-channels-btn");

    const currentChannelTitle = document.getElementById("current-channel-title");
    const videoCountBadge = document.getElementById("video-count-badge");
    const transcriptSearchInput = document.getElementById("transcript-search-input");
    const videoGrid = document.getElementById("video-grid");

    const transcriptViewerSection = document.getElementById("transcript-viewer-section");
    const activeVideoTitle = document.getElementById("active-video-title");
    const activeVideoDate = document.getElementById("active-video-date");
    const activeVideoDuration = document.getElementById("active-video-duration");
    const activeVideoWords = document.getElementById("active-video-words");
    const activeVideoLink = document.getElementById("active-video-link");
    const exportMdBtn = document.getElementById("export-md-btn");
    const exportSrtBtn = document.getElementById("export-srt-btn");
    const aiAnalyzeBtn = document.getElementById("ai-analyze-btn");
    const transcriptContent = document.getElementById("transcript-content");

    const aiWorkspaceSection = document.getElementById("ai-workspace-section");
    const closeAiBtn = document.getElementById("close-ai-btn");
    const aiProviderSelect = document.getElementById("ai-provider-select");
    const aiPromptInput = document.getElementById("ai-prompt-input");
    const runAiAnalysisBtn = document.getElementById("run-ai-analysis-btn");
    const aiResultBox = document.getElementById("ai-result-box");

    // State Variables
    let currentChannelData = null;
    let currentVideoRecord = null;
    let activeJobId = null;
    let pollInterval = null;

    // Toggle Custom Date Inputs
    periodSelect.addEventListener("change", () => {
        if (periodSelect.value === "custom") {
            customDateContainer.classList.remove("hidden");
        } else {
            customDateContainer.classList.add("hidden");
        }
    });

    // Initial Load
    fetchChannels();

    // Form Submit: Trigger Extraction
    extractForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const channel = channelInput.value.trim();
        const period = periodSelect.value;

        if (!channel) return;

        const payload = { channel, period };
        if (period === "custom") {
            payload.start_date = startDateInput.value;
            payload.end_date = endDateInput.value;
        }

        startExtraction(payload);
    });

    async function startExtraction(payload) {
        setExtractingState(true);
        logBox.innerHTML = "";
        progressContainer.classList.remove("hidden");
        updateProgress(0, "Initiating extraction task...");

        try {
            const res = await fetch("/api/extract", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            
            if (data.job_id) {
                activeJobId = data.job_id;
                pollJobStatus();
            } else {
                showError("Failed to start job: " + JSON.stringify(data));
                setExtractingState(false);
            }
        } catch (err) {
            showError("Network error starting extraction: " + err.message);
            setExtractingState(false);
        }
    }

    function pollJobStatus() {
        if (pollInterval) clearInterval(pollInterval);

        pollInterval = setInterval(async () => {
            if (!activeJobId) return;

            try {
                const res = await fetch(`/api/jobs/${activeJobId}`);
                const job = await res.json();

                updateProgress(job.progress, job.status);
                if (job.logs && job.logs.length > 0) {
                    logBox.innerHTML = job.logs.map(l => `<div>${l}</div>`).join("");
                    logBox.scrollTop = logBox.scrollHeight;
                }

                if (job.status === "completed") {
                    clearInterval(pollInterval);
                    setExtractingState(false);
                    fetchChannels();
                    if (job.result && job.result.channel_handle) {
                        selectChannel(job.result.channel_handle);
                    }
                } else if (job.status === "failed") {
                    clearInterval(pollInterval);
                    setExtractingState(false);
                    showError("Extraction failed: " + job.error);
                }
            } catch (err) {
                console.error("Polling error:", err);
            }
        }, 1500);
    }

    function updateProgress(pct, statusText) {
        progressBar.style.width = `${pct}%`;
        progressPercentage.textContent = `${pct}%`;
        progressStatusText.textContent = statusText;
    }

    function setExtractingState(isExtracting) {
        if (isExtracting) {
            extractBtn.disabled = true;
            btnSpinner.classList.remove("hidden");
        } else {
            extractBtn.disabled = false;
            btnSpinner.classList.add("hidden");
        }
    }

    function showError(msg) {
        logBox.innerHTML += `<div style="color:#f43f5e;font-weight:bold;">${msg}</div>`;
    }

    // Refresh Channels List
    refreshChannelsBtn.addEventListener("click", fetchChannels);

    async function fetchChannels() {
        try {
            const res = await fetch("/api/channels");
            const data = await res.json();
            renderChannelsList(data.channels || []);
        } catch (err) {
            console.error("Error fetching channels:", err);
        }
    }

    function renderChannelsList(channels) {
        if (!channels || channels.length === 0) {
            channelsList.innerHTML = `<div class="empty-state">No extracted channels found yet.</div>`;
            return;
        }

        channelsList.innerHTML = channels.map(ch => `
            <div class="channel-item" data-handle="${ch.channel_handle}">
                <div class="channel-item-title">@${ch.channel_handle}</div>
                <div class="channel-item-meta">${ch.video_count || 0} videos • ${ch.period || '3m'}</div>
            </div>
        `).join("");

        document.querySelectorAll(".channel-item").forEach(item => {
            item.addEventListener("click", () => {
                const handle = item.getAttribute("data-handle");
                selectChannel(handle);
            });
        });
    }

    async function selectChannel(handle) {
        document.querySelectorAll(".channel-item").forEach(el => {
            el.classList.toggle("active", el.getAttribute("data-handle") === handle);
        });

        try {
            const res = await fetch(`/api/channels/${handle}`);
            currentChannelData = await res.json();
            
            currentChannelTitle.textContent = `@${currentChannelData.channel_handle} Videos`;
            videoCountBadge.textContent = `${currentChannelData.total_videos_found || 0} videos`;
            
            renderVideoGrid(currentChannelData.videos || []);
        } catch (err) {
            console.error("Failed to load channel details:", err);
        }
    }

    function renderVideoGrid(videos) {
        if (!videos || videos.length === 0) {
            videoGrid.innerHTML = `<div class="empty-state">No videos found for this period.</div>`;
            return;
        }

        videoGrid.innerHTML = videos.map(vid => `
            <div class="video-card" data-id="${vid.video_id}">
                <div class="thumb-container">
                    <img src="${vid.thumbnail}" alt="${vid.title}" loading="lazy">
                    <span class="video-card-duration">${vid.duration_str}</span>
                </div>
                <div class="video-card-body">
                    <div class="video-card-title">${vid.title}</div>
                    <div class="video-card-meta">
                        <span>📅 ${vid.upload_date}</span>
                        <span>👁️ ${vid.view_count ? vid.view_count.toLocaleString() : 'N/A'}</span>
                    </div>
                </div>
            </div>
        `).join("");

        document.querySelectorAll(".video-card").forEach(card => {
            card.addEventListener("click", () => {
                const vidId = card.getAttribute("data-id");
                loadVideoTranscript(currentChannelData.channel_handle, vidId);
            });
        });
    }

    // Filter videos & transcripts via search input
    transcriptSearchInput.addEventListener("input", (e) => {
        const query = e.target.value.toLowerCase().trim();
        if (!currentChannelData || !currentChannelData.videos) return;

        if (!query) {
            renderVideoGrid(currentChannelData.videos);
            return;
        }

        const filtered = currentChannelData.videos.filter(v => 
            v.title.toLowerCase().includes(query) || v.upload_date.includes(query)
        );
        renderVideoGrid(filtered);
    });

    async function loadVideoTranscript(handle, videoId) {
        document.querySelectorAll(".video-card").forEach(c => {
            c.classList.toggle("active", c.getAttribute("data-id") === videoId);
        });

        try {
            const res = await fetch(`/api/channels/${handle}/videos/${videoId}`);
            currentVideoRecord = await res.json();

            const meta = currentVideoRecord.metadata || {};
            const transcript = currentVideoRecord.transcript || {};

            activeVideoTitle.textContent = meta.title || "Untitled Video";
            activeVideoDate.textContent = `📅 ${meta.upload_date}`;
            activeVideoDuration.textContent = `⏱️ ${meta.duration_str}`;
            activeVideoWords.textContent = `📝 ${transcript.word_count || 0} words`;
            activeVideoLink.href = meta.url || `https://www.youtube.com/watch?v=${videoId}`;

            renderTranscriptSegments(transcript.segments || [], videoId);
            transcriptViewerSection.classList.remove("hidden");
            transcriptViewerSection.scrollIntoView({ behavior: "smooth" });
        } catch (err) {
            console.error("Failed to load video transcript:", err);
        }
    }

    function renderTranscriptSegments(segments, videoId) {
        if (!segments || segments.length === 0) {
            transcriptContent.innerHTML = `<div class="empty-state">No transcript available for this video.</div>`;
            return;
        }

        transcriptContent.innerHTML = segments.map(seg => {
            const startSec = Math.floor(seg.start || 0);
            const ytTimestampUrl = `https://youtu.be/${videoId}?t=${startSec}`;
            return `
                <div class="transcript-segment">
                    <a href="${ytTimestampUrl}" target="_blank" class="timestamp-link" title="Jump to timestamp on YouTube">[${seg.start_formatted}]</a>
                    <div class="segment-text">${seg.text}</div>
                </div>
            `;
        }).join("");
    }

    // Export Buttons
    exportMdBtn.addEventListener("click", () => downloadExport("md"));
    exportSrtBtn.addEventListener("click", () => downloadExport("srt"));

    function downloadExport(format) {
        if (!currentChannelData) return;
        const handle = currentChannelData.channel_handle;
        window.location.href = `/api/export/${handle}?format=${format}`;
    }

    // AI Workspace Stub Actions
    aiAnalyzeBtn.addEventListener("click", () => {
        aiWorkspaceSection.classList.remove("hidden");
        aiWorkspaceSection.scrollIntoView({ behavior: "smooth" });
    });

    closeAiBtn.addEventListener("click", () => {
        aiWorkspaceSection.classList.add("hidden");
    });

    runAiAnalysisBtn.addEventListener("click", async () => {
        if (!currentVideoRecord) return;
        const meta = currentVideoRecord.metadata || {};
        
        aiResultBox.innerHTML = `<div class="spinner"></div> Running AI Analysis Stub...`;

        try {
            const res = await fetch("/api/ai/analyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    video_id: meta.video_id,
                    channel: currentChannelData.channel_handle,
                    prompt: aiPromptInput.value,
                    provider: aiProviderSelect.value
                })
            });
            const data = await res.json();

            aiResultBox.innerHTML = `
                <div style="margin-bottom: 10px;">
                    <strong style="color: var(--accent-purple);">Provider:</strong> ${data.provider} | <strong>Status:</strong> ${data.status}
                </div>
                <div style="font-weight: 600; margin-bottom: 8px;">${data.summary}</div>
                <ul style="padding-left: 20px; margin-bottom: 12px;">
                    ${(data.key_insights || []).map(i => `<li>${i}</li>`).join("")}
                </ul>
                <div style="font-weight: 600; margin-bottom: 6px;">Timestamped Takeaways:</div>
                <div style="display: flex; flex-direction: column; gap: 4px;">
                    ${(data.timestamped_takeaways || []).map(t => `<div>${t}</div>`).join("")}
                </div>
                <div style="margin-top: 12px; font-size: 0.78rem; color: var(--text-dim); border-top: 1px solid var(--border-color); padding-top: 6px;">
                    ℹ️ ${data.note}
                </div>
            `;
        } catch (err) {
            aiResultBox.innerHTML = `<div style="color:var(--accent-rose);">Analysis error: ${err.message}</div>`;
        }
    });
});
