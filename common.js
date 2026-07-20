async function loadData() {
  const [entitiesRes, liveRes] = await Promise.all([
    fetch('data/entities.json'),
    fetch('data/live_data.json'),
  ]);
  const entitiesJson = await entitiesRes.json();
  const liveData = await liveRes.json();
  return { entities: entitiesJson.entities, liveData };
}

function formatEuro(n) {
  if (n === null || n === undefined) return null;
  return n.toLocaleString('fr-FR') + ' €';
}

function mergeOrg(entity, liveData) {
  const live = entity.register_id ? liveData[entity.register_id] : null;
  const hasRegisterId = !!entity.register_id;

  const budgetLow = (live && live.budget_low != null) ? live.budget_low : entity.budget_low;
  const budgetHigh = (live && live.budget_high != null) ? live.budget_high : entity.budget_high;
  const peopleInvolved = (live && live.people_involved != null) ? live.people_involved : entity.people_involved;
  const nbIntermediaries = (live && live.nb_intermediaries != null) ? live.nb_intermediaries : entity.nb_intermediaries;
  const intermediariesNames = (live && live.intermediaries_current_year) ? live.intermediaries_current_year : null;

  const epMeetings = live && live.ep_meetings ? live.ep_meetings.since_2025_count : null;
  const ecMeetings = live && live.ec_meetings ? live.ec_meetings.since_2025_count : null;
  const epMeetingsList = (live && live.ep_meetings && live.ep_meetings.since_2025) ? live.ep_meetings.since_2025 : [];
  const ecMeetingsList = (live && live.ec_meetings && live.ec_meetings.since_2025) ? live.ec_meetings.since_2025 : [];

  return {
    name: entity.name,
    type: entity.type || '',
    section: entity.section || '',
    hqAddress: entity.hq_address || '',
    dateRegistration: entity.date_registration || '',
    registerUrl: entity.register_url || null,
    registerId: entity.register_id || null,
    hasRegisterId,
    budgetLow, budgetHigh,
    peopleInvolved,
    nbIntermediaries,
    intermediariesNames,
    epMeetings,
    ecMeetings,
    epMeetingsList,
    ecMeetingsList,
    lobbyfactsStatus: live && live.lobbyfacts ? live.lobbyfacts.status : null,
    lobbyfactsSnapshot: live && live.lobbyfacts ? live.lobbyfacts.snapshot_date : null,
  };
}

function ecMeetingDG(representativeOrDg) {
  const raw = representativeOrDg || '';
  const cabinetMatch = raw.match(/Cabinet member of (.+)$/i);
  if (cabinetMatch) return `Cabinet de ${cabinetMatch[1].trim()}`;
  const parts = raw.split(',').map(s => s.trim()).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : null;
}

function formatDate(isoDate) {
  if (!isoDate) return '—';
  const d = new Date(isoDate);
  if (isNaN(d)) return isoDate;
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function formatFullDate(isoDate) {
  if (!isoDate) return '—';
  const d = new Date(isoDate);
  if (isNaN(d)) return isoDate;
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
}

function setupTableToggle({ tbodyId, wrapperId, btnId, total, initialCount, labelPrefix }) {
  const wrapper = document.getElementById(wrapperId);
  const btn = document.getElementById(btnId);
  const tbody = document.getElementById(tbodyId);

  if (total <= initialCount) {
    wrapper.style.display = 'none';
    return;
  }

  const collapsedLabel = `${labelPrefix} (${total})`;
  btn.textContent = collapsedLabel;

  btn.addEventListener('click', () => {
    const expanded = tbody.classList.toggle('show-all');
    btn.textContent = expanded ? 'Réduire' : collapsedLabel;
  });
}

function setupCollapsible(toggleId, bodyId) {
  const toggle = document.getElementById(toggleId);
  const body = document.getElementById(bodyId);
  toggle.addEventListener('click', () => {
    const isOpen = body.classList.toggle('open');
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  });
}

/* ---------- Tableau des organisations (accueil : aperçu, organisations.html : complet) ---------- */

function renderOrgTable(orgs, tbodyId, initialCount) {
  const tbody = document.getElementById(tbodyId);
  const rows = [];

  orgs.forEach((org, i) => {
    const extraClass = i >= initialCount ? ' extra-row' : '';
    const budget = formatEuro(org.budgetHigh);
    const unregisteredBadge = !org.hasRegisterId
      ? '<span class="unregistered-badge">non enregistrée</span>'
      : '';

    rows.push(`
      <tr class="org-row${extraClass}" data-index="${i}">
        <td data-label="Organisation">${org.name} ${unregisteredBadge}</td>
        <td data-label="Type">${org.type}</td>
        <td class="num" data-label="Budget annuel">${budget ?? '<span class="muted">n.c.</span>'}</td>
        <td class="num" data-label="Personnes">${org.peopleInvolved ?? '<span class="muted">n.c.</span>'}</td>
        <td class="num" data-label="Cabinets">${org.nbIntermediaries ?? '<span class="muted">n.c.</span>'}</td>
        <td class="num" data-label="Réunions PE">${org.hasRegisterId ? (org.epMeetings ?? '<span class="muted">n.c.</span>') : '<span class="muted">non enregistrée</span>'}</td>
        <td class="num" data-label="Réunions Commission">${org.hasRegisterId ? (org.ecMeetings ?? '<span class="muted">n.c.</span>') : '<span class="muted">non enregistrée</span>'}</td>
      </tr>
    `);

    const intermediariesHtml = (org.intermediariesNames && org.intermediariesNames.length)
      ? `<ul class="intermediaries-list">${org.intermediariesNames.map(n => `<li>${n}</li>`).join('')}</ul>`
      : '<span class="muted">Aucun / non communiqué</span>';

    rows.push(`
      <tr class="detail-row${extraClass}" id="${tbodyId}-detail-${i}">
        <td colspan="7">
          <div class="detail-grid">
            <div>
              <dt>Type</dt><dd>${org.type || '—'}</dd>
              <dt>Section</dt><dd>${org.section || '—'}</dd>
              <dt>Siège</dt><dd>${org.hqAddress || '—'}</dd>
            </div>
            <div>
              <dt>Enregistrée depuis</dt><dd>${org.dateRegistration || '—'}</dd>
              <dt>Statut LobbyFacts</dt><dd>${org.lobbyfactsStatus || '—'}${org.lobbyfactsSnapshot ? ` (instantané du ${org.lobbyfactsSnapshot.slice(0,10)})` : ''}</dd>
            </div>
            <div>
              <dt>Cabinets / consultants (exercice en cours)</dt>
              <dd>${intermediariesHtml}</dd>
            </div>
          </div>
          ${org.registerUrl
            ? `<a class="register-link" href="${org.registerUrl}" target="_blank" rel="noopener">Voir la fiche officielle du registre de transparence →</a>`
            : '<p class="muted">Organisation non enregistrée au registre de transparence de l\'UE.</p>'}
        </td>
      </tr>
    `);
  });

  tbody.innerHTML = rows.join('');

  tbody.querySelectorAll('tr.org-row').forEach(row => {
    row.addEventListener('click', () => {
      const detail = document.getElementById(`${tbodyId}-detail-${row.dataset.index}`);
      detail.classList.toggle('open');
    });
  });
}

/* ---------- Eurodéputés les plus rencontrés ---------- */

function computeTopMeps(orgs, limit, epOutsideList) {
  const meps = new Map();

  orgs.forEach(org => {
    org.epMeetingsList.forEach(m => {
      if (!m.member_name) return;
      const entry = meps.get(m.member_name) || { count: 0, latest: null };
      entry.count += 1;
      if (!entry.latest || (m.date || '') > (entry.latest.date || '')) {
        entry.latest = {
          date: m.date,
          orgName: org.name,
          registerUrl: org.registerUrl,
          subject: m.title || null,
          procedureRef: m.procedure_reference || null,
        };
      }
      meps.set(m.member_name, entry);
    });
  });

  (epOutsideList || []).forEach(m => {
    if (!m.member_name) return;
    const attendees = m.attendees || [];
    if (attendees.some(isExcludedFromLobbySearch)) return;

    const entry = meps.get(m.member_name) || { count: 0, latest: null };
    entry.count += 1;
    if (!entry.latest || (m.date || '') > (entry.latest.date || '')) {
      entry.latest = {
        date: m.date,
        orgName: attendees.length ? attendees.join(', ') : 'Acteur non identifié',
        registerUrl: null,
        subject: m.title || null,
        procedureRef: m.procedure_reference || null,
      };
    }
    meps.set(m.member_name, entry);
  });

  return Array.from(meps.entries())
    .map(([name, entry]) => ({ name, count: entry.count, latest: entry.latest }))
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}

function renderTopMeps(topMeps, tbodyId, initialCount) {
  const tbody = document.getElementById(tbodyId);
  if (!topMeps.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="muted">Aucune donnée disponible.</td></tr>';
    return;
  }

  const rows = [];
  topMeps.forEach((mep, i) => {
    const extraClass = i >= initialCount ? ' extra-row' : '';

    rows.push(`
      <tr class="org-row${extraClass}" data-index="${i}">
        <td class="rank" data-label="Rang">${i + 1}</td>
        <td data-label="Eurodéputé">${mep.name}</td>
        <td class="num" data-label="Réunions">${mep.count}</td>
      </tr>
    `);

    const latest = mep.latest;
    rows.push(`
      <tr class="detail-row${extraClass}" id="${tbodyId}-detail-${i}">
        <td colspan="3">
          <div class="detail-grid">
            <div>
              <dt>Organisation rencontrée</dt><dd>${latest.orgName}</dd>
              <dt>Date de la réunion</dt><dd>${formatFullDate(latest.date)}</dd>
              ${latest.subject ? `<dt>Sujet</dt><dd>${latest.subject}</dd>` : ''}
              ${latest.procedureRef ? `<dt>Dossier législatif</dt><dd>${latest.procedureRef}</dd>` : ''}
            </div>
          </div>
          ${latest.registerUrl
            ? `<a class="register-link" href="${latest.registerUrl}" target="_blank" rel="noopener">Voir la fiche officielle du registre de transparence →</a>`
            : '<p class="muted" style="margin: 0.5rem 0 0;">Organisation non enregistrée au registre de transparence de l\'UE.</p>'}
        </td>
      </tr>
    `);
  });

  tbody.innerHTML = rows.join('');

  tbody.querySelectorAll('tr.org-row').forEach(row => {
    row.addEventListener('click', () => {
      const detail = document.getElementById(`${tbodyId}-detail-${row.dataset.index}`);
      detail.classList.toggle('open');
    });
  });
}

/* ---------- Répartition par nationalité des eurodéputés rencontrés ---------- */

const NATIONALITY_CHART_COLORS = ['#0038FF', '#e8590c', '#10b981', '#7c3aed', '#d63384', '#f59e0b', '#0ea5e9', '#84cc16', '#94a3b8'];

function computeMepNationalityBreakdown(orgs, mepCountries) {
  const counts = new Map();

  orgs.forEach(org => {
    org.epMeetingsList.forEach(m => {
      const info = m.member_id ? mepCountries[String(m.member_id)] : null;
      const country = info ? info.country_name : 'Non identifié';
      counts.set(country, (counts.get(country) || 0) + 1);
    });
  });

  return Array.from(counts.entries())
    .map(([country, count]) => ({ country, count }))
    .sort((a, b) => b.count - a.count);
}

function renderNationalityPieChart(breakdown, containerId) {
  const container = document.getElementById(containerId);

  if (!breakdown.length) {
    container.innerHTML = '<p class="muted">Aucune donnée disponible.</p>';
    return;
  }

  const TOP_N = 8;
  const top = breakdown.slice(0, TOP_N);
  const restTotal = breakdown.slice(TOP_N).reduce((sum, d) => sum + d.count, 0);
  const slices = restTotal > 0 ? top.concat([{ country: 'Autres', count: restTotal }]) : top;
  const total = slices.reduce((sum, s) => sum + s.count, 0);

  const size = 180;
  const radius = 70;
  const strokeWidth = 36;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * radius;

  let offset = 0;
  let arcs = '';
  slices.forEach((s, i) => {
    const fraction = s.count / total;
    const dash = fraction * circumference;
    const color = NATIONALITY_CHART_COLORS[i % NATIONALITY_CHART_COLORS.length];
    arcs += `
      <circle cx="${cx}" cy="${cy}" r="${radius}" fill="none" stroke="${color}" stroke-width="${strokeWidth}"
        stroke-dasharray="${dash.toFixed(2)} ${(circumference - dash).toFixed(2)}"
        stroke-dashoffset="${(-offset).toFixed(2)}" transform="rotate(-90 ${cx} ${cy})">
        <title>${s.country} : ${s.count} réunion${s.count === 1 ? '' : 's'} (${Math.round(fraction * 100)}%)</title>
      </circle>
    `;
    offset += dash;
  });

  const legend = slices.map((s, i) => `
    <span class="chart-legend-item">
      <span class="chart-legend-dot" style="background:${NATIONALITY_CHART_COLORS[i % NATIONALITY_CHART_COLORS.length]}"></span>
      ${s.country} (${s.count})
    </span>
  `).join('');

  container.innerHTML = `
    <svg viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg" style="width: 100%; max-width: 220px; height: auto; display: block; margin: 0 auto;">
      ${arcs}
    </svg>
    <div class="chart-legend" style="justify-content: center; text-align: center;">${legend}</div>
  `;
}

/* ---------- Dernières réunions (organisations suivies + recherche mots-clés PE) ---------- */

const EXCLUDED_LOBBY_SEARCH_NAMES = [
  'Smoke Free Partnership',
  'Contre-Feu',
  'Contre feu', // variante sans tiret utilisée par certaines entrées Commission
  'European Respiratory Society',
  'Association of European Cancer Leagues',
  'European Society of Cardiology',
  'European Cancer Organisation',
  'European Alcohol Policy Alliance',
  'Danish Cancer Society',
  'Kræftens Bekæmpelse', // Danish Cancer Society, nom danois
  'European Chronic Disease Alliance',
  'Lung Cancer Europe',
  'Fondation Cancer',
  'Swedish Childhood Cancer Fund',
  'Terveyden ja hyvinvoinnin laitos', // institut finlandais de santé publique (THL)
  'No Plastic Filter',
];

function isExcludedFromLobbySearch(name) {
  const lower = (name || '').toLowerCase();
  return EXCLUDED_LOBBY_SEARCH_NAMES.some(excluded => lower.includes(excluded.toLowerCase()));
}

function computeLatestMeetings(orgs, epOutsideList, ecOutsideList) {
  const combined = [];

  orgs.forEach(org => {
    org.epMeetingsList.forEach(m => {
      combined.push({
        date: m.date,
        orgName: org.name,
        institution: 'parliament',
        dg: null,
        subject: m.title || null,
        procedureRef: m.procedure_reference || null,
        registerUrl: org.registerUrl,
      });
    });
    org.ecMeetingsList.forEach(m => {
      combined.push({
        date: m.date,
        orgName: org.name,
        institution: 'commission',
        dg: ecMeetingDG(m.representative_or_dg),
        subject: null,
        procedureRef: null,
        registerUrl: org.registerUrl,
      });
    });
  });

  (epOutsideList || []).forEach(m => {
    const attendees = m.attendees || [];
    if (attendees.some(isExcludedFromLobbySearch)) return;

    combined.push({
      date: m.date,
      orgName: attendees.length ? attendees.join(', ') : 'Acteur non identifié',
      institution: 'parliament',
      dg: null,
      subject: m.title || null,
      procedureRef: m.procedure_reference || null,
      registerUrl: null,
    });
  });

  (ecOutsideList || []).forEach(m => {
    if (isExcludedFromLobbySearch(m.org)) return;

    combined.push({
      date: m.date,
      orgName: m.org || 'Acteur non identifié',
      institution: 'commission',
      dg: m.dg || null,
      subject: m.subject || null,
      procedureRef: null,
      registerUrl: null,
    });
  });

  const seen = new Set();
  const deduped = combined.filter(m => {
    const key = `${m.date}|${m.institution}|${m.orgName}|${m.subject}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  deduped.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  return deduped.slice(0, 5);
}

function renderLatestMeetings(latest, containerId) {
  const container = document.getElementById(containerId);

  if (!latest.length) {
    container.innerHTML = '<div class="meeting-item"><span class="muted">Aucune réunion récente disponible.</span></div>';
    return;
  }

  const rows = [];
  latest.forEach((m, i) => {
    const institutionLabel = m.institution === 'parliament' ? 'Parlement européen' : 'Commission européenne';

    rows.push(`
      <div class="meeting-item" data-index="${i}">
        <span class="meeting-date">${formatDate(m.date)}</span>
        <span class="meeting-org">
          ${m.orgName}
          ${m.dg ? `<span class="meeting-dg">${m.dg}</span>` : ''}
        </span>
        <span class="institution-badge ${m.institution}">${m.institution === 'parliament' ? 'Parlement' : 'Commission'}</span>
      </div>
    `);

    rows.push(`
      <div class="meeting-detail" id="${containerId}-detail-${i}">
        <div class="detail-grid">
          <div>
            <dt>Organisation</dt><dd>${m.orgName}</dd>
            <dt>Institution</dt><dd>${institutionLabel}</dd>
            ${m.dg ? `<dt>DG concernée</dt><dd>${m.dg}</dd>` : ''}
            ${m.subject ? `<dt>Sujet</dt><dd>${m.subject}</dd>` : ''}
            ${m.procedureRef ? `<dt>Dossier législatif</dt><dd>${m.procedureRef}</dd>` : ''}
            <dt>Date complète</dt><dd>${formatFullDate(m.date)}</dd>
          </div>
        </div>
        ${m.registerUrl
          ? `<a class="register-link" href="${m.registerUrl}" target="_blank" rel="noopener">Voir la fiche officielle du registre de transparence →</a>`
          : '<p class="muted" style="margin: 0.5rem 0 0;">Organisation non enregistrée au registre de transparence de l\'UE.</p>'}
      </div>
    `);
  });

  container.innerHTML = rows.join('');

  container.querySelectorAll('.meeting-item').forEach(item => {
    item.addEventListener('click', () => {
      const detail = document.getElementById(`${containerId}-detail-${item.dataset.index}`);
      detail.classList.toggle('open');
    });
  });
}

/* ---------- Totaux combinés (organisations suivies + acteurs hors liste) ---------- */

function computeCombinedMeetingTotals(aggregate, epOutsideList, ecOutsideList) {
  const epExtra = (epOutsideList || []).filter(m => !(m.attendees || []).some(isExcludedFromLobbySearch)).length;
  const ecExtra = (ecOutsideList || []).filter(m => !isExcludedFromLobbySearch(m.org)).length;

  return Object.assign({}, aggregate, {
    ep_meetings_since_2025_total: (aggregate.ep_meetings_since_2025_total || 0) + epExtra,
    ec_meetings_since_2025_total: (aggregate.ec_meetings_since_2025_total || 0) + ecExtra,
  });
}

/* ---------- Organisations hors liste (organisations.html) ---------- */

function computeOutsideOrganisations(epOutsideList, ecOutsideList) {
  const orgs = new Map();

  (epOutsideList || []).forEach(m => {
    (m.attendees || []).forEach(name => {
      if (!name || isExcludedFromLobbySearch(name)) return;
      const current = orgs.get(name);
      if (!current || (m.date || '') > current) orgs.set(name, m.date || '');
    });
  });

  (ecOutsideList || []).forEach(m => {
    const name = m.org;
    if (!name || isExcludedFromLobbySearch(name)) return;
    const current = orgs.get(name);
    if (!current || (m.date || '') > current) orgs.set(name, m.date || '');
  });

  return Array.from(orgs.entries())
    .map(([name, lastDate]) => ({ name, lastDate }))
    .sort((a, b) => (b.lastDate || '').localeCompare(a.lastDate || ''));
}

function renderOutsideOrganisations(list, tbodyId) {
  const tbody = document.getElementById(tbodyId);

  if (!list.length) {
    tbody.innerHTML = '<tr><td colspan="2" class="muted">Aucune organisation détectée.</td></tr>';
    return;
  }

  tbody.innerHTML = list.map(org => `
    <tr>
      <td data-label="Organisation">${org.name}</td>
      <td data-label="Dernier rendez-vous">${formatDate(org.lastDate)}</td>
    </tr>
  `).join('');
}
