import os
import json
from typing import Dict, Any, List
from jinja2 import Template

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reference Verification Report</title>
    <!-- Modern Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    
    <style>
        :root {
            --bg-dark: #0f172a;
            --bg-card: #1e293b;
            --border-color: #334155;
            
            --color-verified: #10b981;
            --color-verified-bg: rgba(16, 185, 129, 0.15);
            
            --color-no-doi: #f59e0b;
            --color-no-doi-bg: rgba(245, 158, 11, 0.15);
            
            --color-legit-llm: #38bdf8;
            --color-legit-llm-bg: rgba(56, 189, 248, 0.15);
            --glow-legit-llm: 0 0 20px rgba(56, 189, 248, 0.2);
            
            --color-review: #8b5cf6;
            --color-review-bg: rgba(139, 92, 246, 0.15);
            
            --color-fake: #f43f5e;
            --color-fake-bg: rgba(244, 63, 94, 0.15);
            --glow-fake: 0 0 25px rgba(244, 63, 94, 0.25);
            
            --color-unverified: #64748b;
            --color-unverified-bg: rgba(100, 116, 139, 0.15);
            --glow-unverified: 0 0 20px rgba(100, 116, 139, 0.1);
            
            --color-not-found: #ef4444;
            --color-not-found-bg: rgba(239, 68, 68, 0.15);
            
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            
            --glow-verified: 0 0 20px rgba(16, 185, 129, 0.2);
            --glow-no-doi: 0 0 20px rgba(245, 158, 11, 0.2);
            --glow-review: 0 0 20px rgba(139, 92, 246, 0.2);
            --glow-not-found: 0 0 20px rgba(239, 68, 68, 0.2);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 2rem 1rem;
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        /* Header Style */
        header {
            margin-bottom: 3rem;
            text-align: center;
            position: relative;
        }

        header h1 {
            font-family: 'Outfit', sans-serif;
            font-size: 2.8rem;
            font-weight: 700;
            background: linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #c084fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
            letter-spacing: -0.02em;
        }

        header p {
            color: var(--text-secondary);
            font-size: 1.1rem;
            max-width: 600px;
            margin: 0 auto;
        }

        /* Summary Dashboard Grid */
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-bottom: 3rem;
        }

        .card {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            text-align: center;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            position: relative;
            overflow: hidden;
        }

        .card:hover {
            transform: translateY(-4px);
        }

        .card.total { border-top: 4px solid var(--text-secondary); }
        .card.verified { border-top: 4px solid var(--color-verified); }
        .card.no-doi { border-top: 4px solid var(--color-no-doi); }
        .card.legitimate-llm { border-top: 4px solid var(--color-legit-llm); }
        .card.review { border-top: 4px solid var(--color-review); }
        .card.fake { border-top: 4px solid var(--color-fake); }
        .card.unverified { border-top: 4px solid var(--color-unverified); }

        .card.verified:hover { box-shadow: var(--glow-verified); }
        .card.no-doi:hover { box-shadow: var(--glow-no-doi); }
        .card.legitimate-llm:hover { box-shadow: var(--glow-legit-llm); }
        .card.review:hover { box-shadow: var(--glow-review); }
        .card.fake:hover { box-shadow: var(--glow-fake); }
        .card.unverified:hover { box-shadow: var(--glow-unverified); }

        .card-val {
            font-family: 'Outfit', sans-serif;
            font-size: 2.5rem;
            font-weight: 700;
            margin: 0.5rem 0;
        }

        .card-label {
            color: var(--text-secondary);
            font-weight: 500;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        /* Controls Section */
        .controls-container {
            display: flex;
            flex-direction: column;
            gap: 1rem;
            margin-bottom: 2rem;
            background: rgba(30, 41, 59, 0.4);
            border: 1px solid var(--border-color);
            padding: 1.25rem;
            border-radius: 16px;
            backdrop-filter: blur(8px);
        }

        @media (min-width: 768px) {
            .controls-container {
                flex-direction: row;
                align-items: center;
                justify-content: space-between;
            }
        }

        .search-wrapper {
            position: relative;
            flex-grow: 1;
            max-width: 500px;
        }

        .search-input {
            width: 100%;
            background-color: var(--bg-dark);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 0.75rem 1rem 0.75rem 2.5rem;
            border-radius: 12px;
            font-size: 1rem;
            font-family: inherit;
            outline: none;
            transition: border-color 0.3s ease;
        }

        .search-input:focus {
            border-color: #6366f1;
        }

        .search-icon {
            position: absolute;
            left: 0.85rem;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            pointer-events: none;
        }

        .filter-buttons {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }

        .btn-filter {
            background-color: var(--bg-dark);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 0.6rem 1.1rem;
            border-radius: 10px;
            font-family: inherit;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .btn-filter:hover {
            color: var(--text-primary);
            border-color: var(--text-secondary);
        }

        .btn-filter.active {
            background-color: #6366f1;
            color: white;
            border-color: #6366f1;
            box-shadow: 0 0 15px rgba(99, 102, 241, 0.4);
        }

        /* Reference List Styles */
        .reference-list {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .ref-item {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            overflow: hidden;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .ref-item.hidden {
            display: none !important;
        }

        .ref-header {
            padding: 1.25rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            user-select: none;
            gap: 1rem;
        }

        .ref-header-left {
            display: flex;
            align-items: center;
            gap: 1rem;
            flex-grow: 1;
            overflow: hidden;
        }

        .ref-id {
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            color: var(--text-muted);
            font-size: 1.1rem;
            min-width: 2.5rem;
        }

        .ref-text {
            font-weight: 500;
            color: var(--text-primary);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 0.98rem;
        }

        .ref-badges {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            flex-shrink: 0;
        }

        .badge {
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            padding: 0.35rem 0.75rem;
            border-radius: 9999px;
            display: inline-block;
        }

        .badge.verified { background-color: var(--color-verified-bg); color: var(--color-verified); border: 1px solid rgba(16, 185, 129, 0.3); }
        .badge.no-doi { background-color: var(--color-no-doi-bg); color: var(--color-no-doi); border: 1px solid rgba(245, 158, 11, 0.3); }
        .badge.legit-llm { background-color: var(--color-legit-llm-bg); color: var(--color-legit-llm); border: 1px solid rgba(56, 189, 248, 0.3); }
        .badge.review { background-color: var(--color-review-bg); color: var(--color-review); border: 1px solid rgba(139, 92, 246, 0.3); }
        .badge.fake { background-color: var(--color-fake-bg); color: var(--color-fake); border: 1px solid rgba(244, 63, 94, 0.3); }
        .badge.unverified { background-color: var(--color-unverified-bg); color: var(--color-unverified); border: 1px solid rgba(100, 116, 139, 0.3); }

        .score-circle {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background-color: var(--bg-dark);
            border: 2px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.8rem;
            font-weight: 700;
            color: var(--text-secondary);
        }

        .score-circle.high { border-color: var(--color-verified); color: var(--color-verified); }
        .score-circle.medium { border-color: var(--color-review); color: var(--color-review); }
        .score-circle.low { border-color: var(--color-unverified); color: var(--color-unverified); }
        .score-circle.fake-circle { border-color: var(--color-fake); color: var(--color-fake); }

        .arrow-icon {
            color: var(--text-muted);
            transition: transform 0.3s ease;
        }

        .ref-item.expanded .arrow-icon {
            transform: rotate(180deg);
        }

        /* Detail Panel Styles */
        .ref-details {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            background-color: rgba(15, 23, 42, 0.5);
            border-top: 1px solid transparent;
        }

        .ref-item.expanded .ref-details {
            max-height: 1000px;
            border-top: 1px solid var(--border-color);
        }

        .details-inner {
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        .details-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 1.5rem;
        }

        @media (min-width: 768px) {
            .details-grid {
                grid-template-columns: 1fr 1fr;
            }
        }

        .details-block {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .details-block h4 {
            color: var(--text-secondary);
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 600;
        }

        .details-block p {
            background-color: rgba(30, 41, 59, 0.5);
            border: 1px solid var(--border-color);
            padding: 1rem;
            border-radius: 10px;
            font-size: 0.95rem;
            color: var(--text-primary);
        }

        .metadata-table {
            width: 100%;
            border-collapse: collapse;
            background-color: rgba(30, 41, 59, 0.5);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            overflow: hidden;
        }

        .metadata-table td {
            padding: 0.75rem 1rem;
            font-size: 0.9rem;
            border-bottom: 1px solid var(--border-color);
        }

        .metadata-table tr:last-child td {
            border-bottom: none;
        }

        .metadata-key {
            color: var(--text-secondary);
            font-weight: 600;
            width: 30%;
        }

        .metadata-val {
            color: var(--text-primary);
        }

        .metadata-val a {
            color: #60a5fa;
            text-decoration: none;
            transition: color 0.2s ease;
        }

        .metadata-val a:hover {
            color: #93c5fd;
            text-decoration: underline;
        }

        .score-breakdown {
            display: flex;
            align-items: center;
            gap: 1.5rem;
            background-color: rgba(30, 41, 59, 0.5);
            border: 1px solid var(--border-color);
            padding: 1rem 1.5rem;
            border-radius: 10px;
        }

        .score-bar-container {
            flex-grow: 1;
            height: 12px;
            background-color: var(--bg-dark);
            border-radius: 9999px;
            overflow: hidden;
            position: relative;
        }

        .score-bar {
            height: 100%;
            border-radius: 9999px;
            transition: width 0.5s ease-out;
        }

        .score-bar.high { background: linear-gradient(90deg, #059669, #10b981); }
        .score-bar.medium { background: linear-gradient(90deg, #38bdf8, #60a5fa); }
        .score-bar.low { background: linear-gradient(90deg, #64748b, #94a3b8); }
        .score-bar.fake-bar { background: linear-gradient(90deg, #dc2626, #ef4444); }

        .score-text {
            font-family: 'Outfit', sans-serif;
            font-size: 1.25rem;
            font-weight: 700;
            min-width: 5rem;
            text-align: right;
        }

        .score-text.high { color: var(--color-verified); }
        .score-text.medium { color: var(--color-legit-llm); }
        .score-text.low { color: var(--color-unverified); }
        .score-text.fake-text { color: var(--color-fake); }
        
        .no-results-msg {
            text-align: center;
            padding: 3rem;
            color: var(--text-muted);
            font-size: 1.1rem;
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Reference Verification Report</h1>
            <p>Verification summary and matching analysis of academic citations.</p>
        </header>

        <!-- Summary Statistics -->
        <section class="dashboard-grid">
            <div class="card total">
                <div class="card-val">{{ summary.total_references }}</div>
                <div class="card-label">Total References</div>
            </div>
            <div class="card verified">
                <div class="card-val">{{ summary.verified }}</div>
                <div class="card-label">Legitimate</div>
            </div>
            <div class="card legitimate-llm">
                <div class="card-val">{{ summary.legitimate_llm }}</div>
                <div class="card-label">Legitimate (LLM)</div>
            </div>
            <div class="card review">
                <div class="card-val">{{ summary.review_required }}</div>
                <div class="card-label">Review Required</div>
            </div>
        </section>

        <!-- Controls (Filters and Search) -->
        <section class="controls-container">
            <div class="search-wrapper">
                <svg class="search-icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="11" cy="11" r="8"></circle>
                    <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
                <input type="text" id="searchInput" class="search-input" placeholder="Search references by title, author, text...">
            </div>
            <div class="filter-buttons">
                <button class="btn-filter active" data-filter="all">All</button>
                <button class="btn-filter" data-filter="VERIFIED">Legitimate</button>
                <button class="btn-filter" data-filter="LEGITIMATE_KNOWN">Legitimate (LLM)</button>
                <button class="btn-filter" data-filter="REVIEW_REQUIRED">Review Required</button>
            </div>
        </section>

        <!-- References List -->
        <section class="reference-list" id="refList">
            {% for ref in references %}
            <div class="ref-item" data-status="{{ ref.status }}" data-text="{{ ref.raw_reference | lower }} {% if ref.matched_metadata %}{{ ref.matched_metadata.title | lower }} {{ ref.matched_metadata.authors | lower }}{% endif %}">
                <div class="ref-header" onclick="toggleDetails(this)">
                    <div class="ref-header-left">
                        <span class="ref-id">#{{ ref.reference_id }}</span>
                        <span class="ref-text" title="{{ ref.raw_reference }}">{{ ref.raw_reference }}</span>
                    </div>
                    <div class="ref-badges">
                        {% if ref.status == 'VERIFIED' %}
                            <span class="badge verified">Legitimate</span>
                            <span class="score-circle high">{{ ref.confidence | int }}</span>
                        {% elif ref.status == 'LEGITIMATE_KNOWN' %}
                            <span class="badge legit-llm">Legitimate (LLM)</span>
                            <span class="score-circle medium">{{ ref.confidence | int }}</span>
                        {% else %}
                            <span class="badge review">Review Required</span>
                            {% if ref.llm_verdict and ref.llm_verdict.verdict == 'SUSPECTED_FAKE' %}
                                <span class="score-circle fake-circle">{{ ref.confidence | int }}</span>
                            {% elif ref.confidence >= 70 %}
                                <span class="score-circle high">{{ ref.confidence | int }}</span>
                            {% elif ref.confidence >= 40 %}
                                <span class="score-circle medium">{{ ref.confidence | int }}</span>
                            {% else %}
                                <span class="score-circle low">{{ ref.confidence | int }}</span>
                            {% endif %}
                        {% endif %}
                        <svg class="arrow-icon" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                    </div>
                </div>
                
                <div class="ref-details">
                    <div class="details-inner">
                        <!-- LLM Verdict Reason Box -->
                        {% if ref.llm_verdict %}
                        {% set is_fake = ref.llm_verdict.verdict == 'SUSPECTED_FAKE' %}
                        <div style="background-color: {% if is_fake %}var(--color-fake-bg){% else %}var(--color-legit-llm-bg){% endif %}; border: 1px solid {% if is_fake %}var(--color-fake){% else %}var(--color-legit-llm){% endif %}; padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">
                            <h4 style="color: {% if is_fake %}var(--color-fake){% else %}var(--color-legit-llm){% endif %}; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; margin-bottom: 0.25rem;">
                                LLM Audit Verdict: {% if is_fake %}Suspected Fake Citation{% else %}Verified Legitimate{% endif %}
                            </h4>
                            <p style="margin: 0; font-size: 0.95rem; color: var(--text-primary);">{{ ref.llm_verdict.reasoning }}</p>
                        </div>
                        {% endif %}

                        <div class="details-grid">
                            <div class="details-block">
                                <h4>Original Reference Text</h4>
                                <p>{{ ref.raw_reference }}</p>
                            </div>
                            
                            <div class="details-block">
                                <h4>Verification Match Details</h4>
                                {% if ref.matched_metadata %}
                                <table class="metadata-table">
                                    <tr>
                                        <td class="metadata-key">Title</td>
                                        <td class="metadata-val">{{ ref.matched_metadata.title }}</td>
                                    </tr>
                                    <tr>
                                        <td class="metadata-key">Authors</td>
                                        <td class="metadata-val">{{ ref.matched_metadata.authors }}</td>
                                    </tr>
                                    <tr>
                                        <td class="metadata-key">Year</td>
                                        <td class="metadata-val">{{ ref.matched_metadata.year or 'N/A' }}</td>
                                    </tr>
                                    <tr>
                                        <td class="metadata-key">Journal</td>
                                        <td class="metadata-val">{{ ref.matched_metadata.journal or 'N/A' }}</td>
                                    </tr>
                                    <tr>
                                        <td class="metadata-key">Publisher</td>
                                        <td class="metadata-val">{{ ref.matched_metadata.publisher or 'N/A' }}</td>
                                    </tr>
                                    <tr>
                                        <td class="metadata-key">DOI/URL</td>
                                        <td class="metadata-val">
                                            {% if ref.matched_metadata.doi %}
                                                <a href="https://doi.org/{{ ref.matched_metadata.doi }}" target="_blank">{{ ref.matched_metadata.doi }}</a>
                                            {% elif ref.matched_metadata.url %}
                                                <a href="{{ ref.matched_metadata.url }}" target="_blank">View Document Link</a>
                                            {% else %}
                                                N/A
                                            {% endif %}
                                        </td>
                                    </tr>
                                </table>
                                {% else %}
                                <p style="color: var(--text-muted); font-style: italic;">No matching database metadata candidate scored high enough to associate.</p>
                                {% endif %}
                            </div>
                        </div>
                        
                        <div class="details-block">
                            <h4>Legitimacy Confidence Level</h4>
                            <div class="score-breakdown">
                                <div class="score-bar-container">
                                    {% if ref.status == 'VERIFIED' %}
                                        <div class="score-bar high" style="width: {{ ref.confidence }}%"></div>
                                    {% elif ref.status == 'LEGITIMATE_KNOWN' %}
                                        <div class="score-bar medium" style="width: {{ ref.confidence }}%"></div>
                                    {% else %}
                                        {% if ref.llm_verdict and ref.llm_verdict.verdict == 'SUSPECTED_FAKE' %}
                                            <div class="score-bar fake-bar" style="width: {{ ref.confidence }}%"></div>
                                        {% elif ref.confidence >= 70 %}
                                            <div class="score-bar high" style="width: {{ ref.confidence }}%"></div>
                                        {% elif ref.confidence >= 40 %}
                                            <div class="score-bar medium" style="width: {{ ref.confidence }}%"></div>
                                        {% else %}
                                            <div class="score-bar low" style="width: {{ ref.confidence }}%"></div>
                                        {% endif %}
                                    {% endif %}
                                </div>
                                <span class="score-text {% if ref.status == 'VERIFIED' %}high{% elif ref.status == 'LEGITIMATE_KNOWN' %}medium{% else %}{% if ref.llm_verdict and ref.llm_verdict.verdict == 'SUSPECTED_FAKE' %}fake-text{% elif ref.confidence >= 70 %}high{% elif ref.confidence >= 40 %}medium{% else %}low{% endif %}{% endif %}">
                                    {{ ref.confidence }}%
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            {% endfor %}
            
            <div id="noResults" class="no-results-msg" style="display: none;">
                No references match the selected search and filter criteria.
            </div>
        </section>
    </div>

    <script>
        function toggleDetails(header) {
            const item = header.closest('.ref-item');
            const isExpanded = item.classList.contains('expanded');
            
            // Close other items
            document.querySelectorAll('.ref-item.expanded').forEach(el => {
                if (el !== item) {
                    el.classList.remove('expanded');
                }
            });
            
            // Toggle current
            if (isExpanded) {
                item.classList.remove('expanded');
            } else {
                item.classList.add('expanded');
            }
        }

        // Filtering and Search Logic
        const searchInput = document.getElementById('searchInput');
        const filterBtns = document.querySelectorAll('.btn-filter');
        const refList = document.getElementById('refList');
        const refItems = document.querySelectorAll('.ref-item');
        const noResults = document.getElementById('noResults');

        let currentFilter = 'all';
        let searchQuery = '';

        function updateList() {
            let visibleCount = 0;

            refItems.forEach(item => {
                const status = item.getAttribute('data-status');
                const text = item.getAttribute('data-text');

                const matchesFilter = (currentFilter === 'all' || status === currentFilter);
                const matchesSearch = text.includes(searchQuery);

                if (matchesFilter && matchesSearch) {
                    item.classList.remove('hidden');
                    visibleCount++;
                } else {
                    item.classList.add('hidden');
                }
            });

            if (visibleCount === 0) {
                noResults.style.display = 'block';
            } else {
                noResults.style.display = 'none';
            }
        }

        // Search Input Event
        searchInput.addEventListener('input', (e) => {
            searchQuery = e.target.value.toLowerCase().trim();
            updateList();
        });

        // Filter Buttons Event
        filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                filterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentFilter = btn.getAttribute('data-filter');
                updateList();
            });
        });
    </script>
</body>
</html>
"""

def generate_report(results: Dict[str, Any], output_dir: str):
    """
    Generates report.json and a visually stunning interactive report.html in output_dir.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Save JSON Report
    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON report to: {json_path}")
    
    # 2. Render HTML Report
    template = Template(HTML_TEMPLATE)
    html_content = template.render(
        summary=results["summary"],
        references=results["references"]
    )
    
    html_path = os.path.join(output_dir, "report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Saved interactive HTML report to: {html_path}")

    # 3. Generate DOCX Report
    docx_path = os.path.join(output_dir, "report.docx")
    try:
        from app.reporting.docx_generator import generate_docx_report
        generate_docx_report(results, docx_path)
    except Exception as e:
        print(f"Failed to generate DOCX report: {e}")

