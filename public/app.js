(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const offline = location.protocol === 'file:' || location.pathname.endsWith('/dashboard.html');
  let snapshot = JSON.parse($('initial-data').textContent || 'null');
  let board = 'Mainboard', query = '', status = 'Unlisted', sortKey = null, sortDir = -1;
  let visible = [], busy = false, localNotice = '', lastError = '';
  const money = value => value == null ? '—' : '₹' + new Intl.NumberFormat('en-IN', {maximumFractionDigits: 2}).format(value);
  const integer = value => value == null ? '—' : new Intl.NumberFormat('en-IN', {maximumFractionDigits: 0}).format(value);
  const pct = value => value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tone = value => value == null || value === 0 ? 'zero' : value > 0 ? 'gain' : 'loss';
  const clock = value => new Intl.DateTimeFormat('en-IN', {day:'numeric',month:'short',hour:'numeric',minute:'2-digit',timeZone:'Asia/Kolkata'}).format(new Date(value));
  const palettes = [['#eaf0ff','#697baf'],['#f4edff','#8d72ae'],['#eaf3e8','#68875e'],['#fff0e8','#ac8063'],['#e5f3f4','#5c9394']];

  function notices() {
    const messages = [];
    if (offline) messages.push('Saved snapshot. Run “python3 app.py” and open http://127.0.0.1:8765 to refresh, or run “python3 app.py --refresh” to update this file.');
    if (localNotice) messages.push(localNotice);
    if (lastError) messages.push(lastError);
    if (snapshot?.warnings?.length) messages.push(`${snapshot.warnings.length} detail pages could not be read. Affected estimates are marked “Calculated” or left unavailable; open a company’s source page to verify.`);
    if (snapshot && Date.now() - new Date(snapshot.fetchedAt).getTime() > 24 * 60 * 60 * 1000) messages.push('This snapshot is more than 24 hours old. Refresh for newer data.');
    $('notice').textContent = messages.join(' ');
    $('notice').hidden = !messages.length;
  }

  function render() {
    const data = snapshot?.rows || [];
    visible = data.filter(row => (board === 'All' || row.board === board) && row.name.toLowerCase().includes(query.toLowerCase()) &&
      (status === 'All' || (status === 'Unlisted' ? row.status !== 'Listed' : status === 'Open' ? ['Open','Closing today'].includes(row.status) : row.status === status)));
    if (sortKey) visible.sort((a,b) => {
      const x = a[sortKey], y = b[sortKey];
      if (x == null) return y == null ? 0 : 1;
      if (y == null) return -1;
      return (typeof x === 'number' ? x-y : x.localeCompare(y)) * sortDir;
    });
    $('count').textContent = visible.length;
    $('stat-count').textContent = snapshot ? visible.length : '—';
    $('stat-open').textContent = snapshot ? visible.filter(r => ['Open','Closing today'].includes(r.status)).length : '—';
    $('stat-scope').textContent = `${board === 'All' ? 'All segments' : board} · ${status}${query ? ' · Search applied' : ''}`;
    for (const [field,id] of [['gmpPercent','gmp'],['profitPerLot','profit']]) {
      const best = visible.filter(r => r[field] != null).reduce((a,b) => !a || b[field] > a[field] ? b : a, null);
      $('stat-'+id).textContent = best ? field === 'gmpPercent' ? pct(best[field]) : money(best[field]) : '—';
      $('stat-'+id).className = best ? tone(best[field]) : 'zero';
      $('stat-'+id+'-name').textContent = best ? best.name : 'No estimate available';
    }
    $('rows').innerHTML = visible.map((r,i) => {
      const initials = r.name.split(/\s+/).slice(0,2).map(s=>s[0]).join('').toUpperCase();
      const colors = palettes[i % palettes.length];
      const statusClass = r.status.toLowerCase().replace(/\s/g,'-');
      const safeUrl = /^https:\/\/www\.investorgain\.com\/gmp\/[^/]+\/\d+\/$/.test(r.url) ? r.url : 'https://www.investorgain.com/report/ipo-gmp-live/331/';
      return `<tr><td><div class="company"><span aria-hidden="true" class="avatar" style="--avatar-bg:${colors[0]};--avatar-color:${colors[1]}">${esc(initials)}</span><div><a href="${esc(safeUrl)}" target="_blank" rel="noopener noreferrer">${esc(r.name)} <span aria-hidden="true" style="color:#b1bdb5;font-size:10px">↗</span></a><small>${esc(r.exchange)} IPO</small></div></div></td>
        <td class="num ${tone(r.gmp)}">${money(r.gmp)}</td>
        <td class="num"><span class="${r.gmpPercent == null ? 'zero' : 'gmp-percent '+tone(r.gmpPercent)}">${pct(r.gmpPercent)}</span></td>
        <td class="num emphasis profit ${tone(r.profitPerLot)}" title="${r.profitSource === 'detail' ? 'Latest estimated profit from the IPO detail page' : r.profitSource === 'calculated' ? 'Detail page unavailable. Calculated from report GMP × lot size.' : 'Profit unavailable until GMP and lot size are known'}">${money(r.profitPerLot)}<span class="subtext">${r.profitSource === 'calculated' ? 'Calculated · detail unavailable' : r.profitPerLot != null ? 'per lot · source estimate' : !r.lotSize ? 'Lot size pending' : 'Not available'}</span></td>
        <td class="num">${money(r.price)}${r.price == null ? '<span class="subtext">Not announced</span>' : ''}</td>
        <td class="num">${integer(r.lotSize)}<span class="subtext">${r.lotSize ? 'shares' : 'Pending'}</span></td>
        <td><span class="pill ${esc(statusClass)}">${esc(r.status)}</span></td>
        <td class="num">${esc(r.issueSize && r.issueSize !== '-' ? r.issueSize : '—')}</td>
        <td class="dates">${esc(r.openDate || '—')} <span class="arrow">→</span> ${esc(r.closeDate || '—')}</td><td class="dates">${esc(r.listingDate || '—')}</td>
        <td><span class="rating" title="InvestorGain rating: ${r.rating} out of 5" aria-label="Source rating: ${r.rating} out of 5">${r.rating ? '★'.repeat(Math.min(5,r.rating))+'<span style="color:#e5e8e3">'+'★'.repeat(Math.max(0,5-r.rating))+'</span>' : '—'}</span></td>
        <td class="dates">${esc(r.sourceUpdated || '—')}${r.detailError ? '<span class="subtext">Report only</span>' : ''}</td></tr>`;
    }).join('');
    $('empty').hidden = !!visible.length || (!snapshot && busy);
    $('showing').textContent = snapshot ? `Showing ${visible.length} of ${data.length} IPOs in the source’s current report` : busy ? 'Fetching the report and IPO detail pages…' : 'No snapshot yet. Refresh to load IPO data.';
    $('export').disabled = !visible.length;
    $('updated').textContent = snapshot ? `Fetched ${clock(snapshot.fetchedAt)} IST` : 'Waiting for first refresh';
    document.querySelectorAll('[data-sort]').forEach(button => {
      button.parentElement.removeAttribute('aria-sort');
      if (button.dataset.sort === sortKey) button.parentElement.setAttribute('aria-sort',sortDir === 1 ? 'ascending' : 'descending');
    });
    notices();
  }

  async function sync() {
    if (offline) return;
    try {
      const response = await fetch('/api/ipos', {cache:'no-store'});
      if (!response.ok) throw new Error('Server returned '+response.status);
      const data = await response.json();
      snapshot = data.snapshot;
      busy = data.refreshing;
      lastError = data.lastError || '';
      $('refresh').disabled = busy;
      $('refresh-icon').classList.toggle('spin',busy);
      $('refresh-label').textContent = busy ? data.progress ? `Reading ${data.progress.done}/${data.progress.total}` : 'Fetching IPOs…' : 'Refresh data';
      render();
    } catch (_) {
      busy = false;
      lastError = 'The local server is unavailable. Start it with “python3 app.py”. Any data shown is the last loaded snapshot.';
      $('refresh').disabled = false;
      $('refresh-icon').classList.remove('spin');
      $('refresh-label').textContent = 'Retry connection';
      notices();
    }
  }

  $('refresh').addEventListener('click',async () => {
    if (offline) { notices(); return; }
    $('refresh').disabled = true;
    localNotice = '';
    try {
      const response = await fetch('/api/refresh', {method:'POST'});
      if (response.status === 429) localNotice = 'Please allow one minute between refreshes.';
      else if (!response.ok) throw new Error('Refresh request failed');
    } catch (_) { localNotice = 'Could not start a refresh. Check that the local server is running.'; }
    await sync();
  });
  document.querySelectorAll('[data-board]').forEach(button => button.addEventListener('click',() => {
    board = button.dataset.board;
    document.querySelectorAll('[data-board]').forEach(b => b.setAttribute('aria-pressed',b === button ? 'true' : 'false'));
    render();
  }));
  document.querySelectorAll('[data-sort]').forEach(button => button.addEventListener('click',() => {
    sortDir = sortKey === button.dataset.sort ? -sortDir : button.dataset.sort === 'name' ? 1 : -1;
    sortKey = button.dataset.sort;
    render();
  }));
  $('search').addEventListener('input',e => { query = e.target.value; render(); });
  $('status').addEventListener('change',e => { status = e.target.value; render(); });
  $('reset').addEventListener('click',() => {
    query = ''; status = 'Unlisted'; $('search').value = ''; $('status').value = status;
    document.querySelector('[data-board="Mainboard"]').click();
  });
  $('export').addEventListener('click',() => {
    const fields = [['Company','name'],['Segment','board'],['Status','status'],['Price INR','price'],['GMP INR','gmp'],['GMP percent','gmpPercent'],['Estimated profit per lot INR','profitPerLot'],['Profit source','profitSource'],['Lot size','lotSize'],['Issue size','issueSize'],['Open','openDate'],['Close','closeDate'],['Listing','listingDate'],['GMP updated IST','sourceUpdated'],['Source URL','url']];
    const cell = value => { let s = String(value ?? ''); if (typeof value === 'string' && /^[=+\-@\t\r]/.test(s)) s = "'"+s; return '"'+s.replace(/"/g,'""')+'"'; };
    const csv = '\ufeff'+[fields.map(f=>cell(f[0])).join(','),...visible.map(r=>fields.map(f=>cell(r[f[1]])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    const a = document.createElement('a'); a.href=url; a.download='ipo-watchlist.csv'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  render();
  if (offline) { $('refresh').disabled = true; $('refresh-label').textContent = 'Saved snapshot'; }
  else { sync(); setInterval(sync,2500); }
})();
