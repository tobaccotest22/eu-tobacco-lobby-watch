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
