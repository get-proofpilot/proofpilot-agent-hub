// ProofPilot SEO Playbook — Agent Hub
// 4 tabs: Framework, Month Calendar, SOP Reference, My Clients
(function(){
var DATA=null, evtSource=null, curFilter='all', curCatFilter='All', calYear, calMonth, expandAll=false;
var CLOCK='<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>';
var CHEVRON='\u25BC';
var MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
var WDAYS=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

// ── SOP DATA (from reference) ──
var SOPs=[
{title:"Service Page",category:"Content",priority:"high",timeMin:90,timeMax:120,steps:[
"Confirm primary target keyword and secondary keywords with rank tracker (5 min)",
"Analyze top 3 SERP competitors — note headings, word count, FAQs, unique angles (10 min)",
"Draft outline: H1, intro, 3-5 H2s, FAQ section, CTA (5 min)",
"Write full page copy focused on service keyword, benefits, local relevance (30 min)",
"Write 4-6 FAQs using People Also Ask and keyword tools (10 min)",
"Optimize title tag (60 chars), meta description (155 chars), H1 (5 min)",
"Add Service/LocalBusiness schema markup (5 min)",
"Add 3-5 internal links to related service and location pages (5 min)",
"Source or create at least 1 image — add descriptive alt text with keyword (5 min)",
"Publish and submit URL to indexing tool (5 min)"]},
{title:"Location Page",category:"Content",priority:"high",timeMin:45,timeMax:60,steps:[
"Research target city — population, neighborhoods, landmarks, local context (5 min)",
"Write 400-600 words of fully unique content (do not duplicate other location pages) (20 min)",
"Add local reference, landmark, or community detail for geographic relevance",
"Embed Google Maps iframe for client GBP location (2 min)",
"Ensure NAP matches GBP exactly (2 min)",
"Apply LocalBusiness schema with city-specific address targeting (5 min)",
"Add internal links from nearest service page and location hub page (5 min)",
"Optimize meta title (include '[Service] in [City, State]') and meta description (5 min)",
"Publish and submit URL to indexing tool (3 min)"]},
{title:"Blog Post",category:"Content",priority:"high",timeMin:60,timeMax:90,steps:[
"Confirm target keyword (informational or comparison intent) and monthly search volume (5 min)",
"Analyze top 5 SERP results — note length, subheadings, gaps (10 min)",
"Write detailed outline with H2/H3 structure and word count target (5 min)",
"Write full post (1,000-1,500 words) with natural, conversational tone (25 min)",
"Source or create at least 2 images — keyword-rich alt text (5 min)",
"Add 3-4 internal links to service pages and related blog posts (5 min)",
"Optimize meta title and description; include keyword naturally (5 min)",
"Add clear CTA at bottom (contact form, phone, service page link) (5 min)",
"Publish and submit URL to indexing tool (3 min)"]},
{title:"Post & Schedule 8 Google Business Posts",category:"Local SEO",priority:"medium",timeMin:30,timeMax:45,steps:[
"Plan 8 post topics — mix service spotlights, seasonal tips, offers, FAQs (5 min)",
"Write short, punchy copy for each post (100-300 chars) with CTA and link (15 min)",
"Source or create images — minimum 750x750px, branded where possible (8 min)",
"Schedule all 8 posts in GBP, spaced 3-4 days apart (7 min)",
"Verify all posts are live and scheduled in GBP dashboard (3 min)"]},
{title:"Citation Buildout (~60 Citations)",category:"Local SEO",priority:"medium",timeMin:60,timeMax:80,steps:[
"Pull next batch of unpublished directories from citation tracker (5 min)",
"Verify NAP matches GBP exactly before submitting (2 min)",
"Submit to each directory from standard NAP template (45-60 min)",
"Log every submission in citation tracker with directory name, URL, date (5 min)",
"Flag any duplicate or inconsistent existing citations for cleanup"]},
{title:"GBP Review Responses (Up to 10)",category:"Local SEO",priority:"medium",timeMin:20,timeMax:30,steps:[
"Open GBP and identify all new reviews since last response session (2 min)",
"Draft AI-assisted response for each review using content as context (10 min)",
"Personalize every response: address by name, reference specific feedback (5 min)",
"Include 1 natural service keyword in positive responses; keep negatives empathetic",
"Never copy-paste identical responses — vary phrasing across all replies",
"Post all responses and log date in tracker (3 min)"]},
{title:"Image Sharing & Geo-Tagging (Up to 60 Images)",category:"Local SEO",priority:"medium",timeMin:45,timeMax:60,steps:[
"Collect up to 60 images (job photos, completed work, team, before/after) (5 min)",
"Rename files: keyword-city-number.jpg (e.g., electrician-orange-ca-01.jpg) (5 min)",
"Add EXIF GPS metadata matching business address using EXIF tool (10 min)",
"Upload to sharing platforms (Flickr, Pinterest, Google Photos, Imgur) (20 min)",
"Write unique keyword-rich descriptions with location info (10 min)",
"Log platforms, upload counts, and date in activity tracker"]},
{title:"500 Map Embed Distribution",category:"Local SEO",priority:"medium",timeMin:30,timeMax:45,steps:[
"Obtain Google Maps iframe embed code for client GBP listing (2 min)",
"Configure distribution tool with embed code and target count of 500 (5 min)",
"Run distribution — largely automated (20-30 min monitored)",
"Verify tool reports successful distribution and note errors (3 min)",
"Screenshot completion report and log date in tracker (3 min)"]},
{title:"Niche Blog Comment Backlinks (5)",category:"Link Building",priority:"medium",timeMin:30,timeMax:45,steps:[
"Find 5 active blogs in client niche with open comments and DA 20+ (10 min)",
"Read each blog post fully — understand topic before commenting (10 min)",
"Write genuine, value-adding comment that extends the conversation (10 min)",
"Include client site URL in Website field (not in body unless natural)",
"Submit and log blog URL, DA, comment date, status in link tracker (5 min)"]},
{title:"Patch Posts (2)",category:"Link Building",priority:"medium",timeMin:20,timeMax:30,steps:[
"Choose 2 local news angles relevant to service area or industry (5 min)",
"Write 150-300 words per post — local news tone, not promotional (10 min)",
"Include business name, city, and contextual link back to website (2 min)",
"Publish both on Patch.com under client market/neighborhood section (5 min)",
"Screenshot live posts and log URL and date in link tracker (3 min)"]},
{title:"Niche & Local Signals (Up to 60 Min)",category:"Link Building",priority:"medium",timeMin:60,timeMax:60,steps:[
"Identify target platforms: Quora, niche forums, local FB groups, community boards (5 min)",
"Participate genuinely — answer questions, share tips, contribute (40 min)",
"Include branded mentions or contextual links where appropriate (10 min)",
"Log all activity with platform, URL, type, date in tracker (5 min)"]},
{title:"Reddit Posts (2)",category:"Link Building",priority:"low",timeMin:20,timeMax:30,steps:[
"Find 2 relevant subreddits (local r/[city], home improvement, niche trade) (5 min)",
"Plan each post around a topic that genuinely helps the community (5 min)",
"Write the post (100-300 words) in conversational first-person tone (10 min)",
"Include link to helpful blog post or resource if contextually appropriate",
"Post both and log subreddit, URL, date in tracker (3 min)",
"Check back within 24-48 hours to respond to comments"]},
{title:"4 Pinterest Pins",category:"Social",priority:"low",timeMin:20,timeMax:30,steps:[
"Select 4 images from blog posts, service pages, or branded assets (3 min)",
"Create pin graphics if needed — min 1000x1500px with text overlay (8 min)",
"Write keyword-rich descriptions (150-500 chars) with natural CTA (5 min)",
"Add target page URL to each pin (1 min)",
"Schedule or publish to relevant boards (3 min)",
"Log pin URLs and board names in social tracker"]},
{title:"1 YouTube Video (Slideshow or Screen Recording)",category:"Social",priority:"low",timeMin:45,timeMax:60,steps:[
"Choose topic: service walkthrough, before/after, FAQ, or screen recording (5 min)",
"Gather screenshots, job photos, or website content as footage (10 min)",
"Create slideshow in Canva/PowerPoint or record screen walkthrough (20 min)",
"Add branded intro/outro, text overlays, background music (5 min)",
"Write SEO title (keyword + location), description (300+ words), 10-15 tags (5 min)",
"Upload to client YouTube channel with custom thumbnail (5 min)",
"Add to playlist and include CTA with website link in description (3 min)"]},
{title:"Monthly SEO Report",category:"Reporting",priority:"high",timeMin:90,timeMax:120,steps:[
"Pull Google Search Console: clicks, impressions, CTR, average position (10 min)",
"Pull GA4: organic sessions, engaged sessions, conversions (10 min)",
"Pull rank tracker: keyword position changes vs prior month (10 min)",
"Pull GBP Insights: calls, directions, profile views, photo views (5 min)",
"Compile data into monthly report template (30 min)",
"Write month summary: top wins, notable drops and why, 3 recommendations (20 min)",
"Quality-check all numbers for accuracy (5 min)",
"Deliver report via email or shared Google Doc; log delivery date (5 min)"]},
{title:"Heat Map Pull (Bi-Weekly)",category:"Reporting",priority:"high",timeMin:15,timeMax:20,steps:[
"Log into heat map tool (Local Dominator) (2 min)",
"Navigate to homepage, top service page, top location page (2 min)",
"Review geo grids and position changes for each page (5 min)",
"Screenshot notable patterns and position improvements (3 min)",
"Document findings with date and key observations (5 min)",
"Flag significant changes for next strategy review"]},
{title:"Press Release",category:"PR",priority:"high",timeMin:45,timeMax:60,steps:[
"Choose announcement: new service, award, milestone, community, news hook (5 min)",
"Write 400-500 word press release in AP style (20 min)",
"Include full NAP and at least 1 dofollow link to homepage or service page (3 min)",
"Review for brand voice and proofread for errors (7 min)",
"Submit to PR distribution service (EIN Presswire, PRWeb, etc.) (5 min)",
"Log distribution date; collect placement URLs when live (5 min)"]},
{title:"Submit All Links to Indexing Tool",category:"Technical SEO",priority:"medium",timeMin:20,timeMax:30,steps:[
"Compile all URLs published or acquired this month: pages, posts, backlinks (10 min)",
"Organize URL list by type (owned pages vs external backlinks) (2 min)",
"Submit full batch to indexing tool (Omega Indexer, GSC URL Inspection) (5 min)",
"Verify tool confirms successful submission with no errors (3 min)",
"Log submission date and URL count in monthly tracker (3 min)"]}
];

var CATEGORIES=["All"];
SOPs.forEach(function(s){ if(CATEGORIES.indexOf(s.category)<0) CATEGORIES.push(s.category); });

var CAT_CHIP={
"Content":"pb-chip-content","Local SEO":"pb-chip-local-seo","Link Building":"pb-chip-link-building",
"Social":"pb-chip-social","Reporting":"pb-chip-reporting","PR":"pb-chip-pr","Technical SEO":"pb-chip-technical-seo"
};
var CAT_CALCHIP={
"Content":"background:rgba(139,92,246,0.12);color:#a78bfa;border-color:rgba(139,92,246,0.25)",
"Local SEO":"background:rgba(59,130,246,0.12);color:#60a5fa;border-color:rgba(59,130,246,0.25)",
"Link Building":"background:rgba(251,146,60,0.12);color:#fb923c;border-color:rgba(251,146,60,0.25)",
"Social":"background:rgba(236,72,153,0.12);color:#f472b6;border-color:rgba(236,72,153,0.25)",
"Reporting":"background:rgba(20,184,166,0.12);color:#2dd4bf;border-color:rgba(20,184,166,0.25)",
"PR":"background:rgba(251,191,36,0.12);color:#fbbf24;border-color:rgba(251,191,36,0.25)",
"Technical SEO":"background:rgba(148,163,184,0.12);color:#94a3b8;border-color:rgba(148,163,184,0.25)"
};

// ── HELPERS ──
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x)e.textContent=x;return e;}
function fmtTime(min,max){if(min===max)return min+'m';return min+'-'+max+'m';}
function fmtMins(m){if(m<60)return m+'m';var h=Math.floor(m/60),r=m%60;return r?h+'h '+r+'m':h+'h';}
function parseHours(t){if(!t||t==='outsource'||t==='varies')return 0;var h=t.match(/(\d+)\s*hr/),m=t.match(/(\d+)\s*min/),r=0;if(h)r+=parseInt(h[1]);if(m)r+=parseInt(m[1])/60;return r;}
function getTotalHours(c){var r=0;Object.keys(c.tasks).forEach(function(k){c.tasks[k].forEach(function(t){r+=parseHours(t.time);});});return r;}
function tc(tier){return 'pb-tier-'+tier;}
function ac(m){return m==='Matthew'?'pb-av-m':m==='Marcos'?'pb-av-marcos':'pb-av-jo';}
function ini(m){return m.split(' ').map(function(w){return w[0];}).join('');}

// ── INIT ──
document.addEventListener('DOMContentLoaded',function(){
  var root=document.getElementById('seo-playbook-root');
  if(!root)return;
  var now=new Date();calYear=now.getFullYear();calMonth=now.getMonth();
  root.appendChild(el('div','pb-loading','Loading playbook data...'));
  fetch('/api/seo/playbook-data').then(function(r){return r.json();}).then(function(d){
    DATA=d;render(root);connectSSE();
  }).catch(function(){root.textContent='';root.appendChild(el('div','pb-loading','Failed to load. Run scripts/sync-vault-data.sh first.'));});
});

function connectSSE(){if(evtSource)evtSource.close();evtSource=new EventSource('/api/seo/events');evtSource.onmessage=function(e){try{handleSSE(JSON.parse(e.data));}catch(err){}};evtSource.onerror=function(){var d=document.getElementById('pb-conn-dot');if(d)d.className='pb-status-dot disconnected';};evtSource.onopen=function(){var d=document.getElementById('pb-conn-dot');if(d)d.className='pb-status-dot connected';};}
function handleSSE(msg){var p=document.getElementById('pb-output-body');if(!p)return;if(msg.type==='start'){var e=el('div','pb-output-entry');e.appendChild(el('div','pb-output-cmd',msg.command));e.appendChild(el('div','pb-output-text'));e.appendChild(el('div','pb-output-status run','Running...'));p.insertBefore(e,p.firstChild);openPanel();}else if(msg.type==='output'){var es=p.querySelectorAll('.pb-output-entry');if(es.length){var t=es[0].querySelector('.pb-output-text');if(t)t.textContent+=msg.text;}}else if(msg.type==='complete'){var es2=p.querySelectorAll('.pb-output-entry');if(es2.length){var s=es2[0].querySelector('.pb-output-status');if(s){s.className='pb-output-status ok';s.textContent='Complete';}}}else if(msg.type==='error'){var es3=p.querySelectorAll('.pb-output-entry');if(es3.length){var s2=es3[0].querySelector('.pb-output-status');if(s2){s2.className='pb-output-status err';s2.textContent='Error: '+(msg.error||'Failed');}}}}
function openPanel(){var p=document.getElementById('pb-output-panel');if(p)p.classList.add('open');}
function closePanel(){var p=document.getElementById('pb-output-panel');if(p)p.classList.remove('open');}
function doRun(cmd){fetch('/api/seo/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:cmd})}).catch(function(){});}
function doBatch(cmds){fetch('/api/seo/batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({commands:cmds})}).catch(function(){});}

// ── RENDER ROOT ──
function render(root){
  root.textContent='';
  var hdr=el('div','pb-header');hdr.appendChild(el('h2','','SEO Operations Playbook'));
  var right=el('div');var dot=el('span','pb-status-dot disconnected');dot.id='pb-conn-dot';right.appendChild(dot);right.appendChild(el('span','','\u00A0'+(DATA.month||'')));hdr.appendChild(right);root.appendChild(hdr);

  var tabs=el('div','pb-tabs');
  var ids=['pb-p-fw','pb-p-cal','pb-p-sop','pb-p-mc'];
  ['Framework','Month Calendar','SOP Reference','My Clients'].forEach(function(name,i){
    var tab=el('div','pb-tab'+(i===0?' active':''),name);
    tab.addEventListener('click',function(){
      tabs.querySelectorAll('.pb-tab').forEach(function(t){t.classList.remove('active');});
      ids.forEach(function(id){var p=document.getElementById(id);if(p)p.classList.remove('active');});
      tab.classList.add('active');document.getElementById(ids[i]).classList.add('active');
    });tabs.appendChild(tab);
  });root.appendChild(tabs);

  var p0=el('div','pb-panel active');p0.id='pb-p-fw';renderFramework(p0);root.appendChild(p0);
  var p1=el('div','pb-panel');p1.id='pb-p-cal';renderCalendar(p1);root.appendChild(p1);
  var p2=el('div','pb-panel');p2.id='pb-p-sop';renderSOP(p2);root.appendChild(p2);
  var p3=el('div','pb-panel');p3.id='pb-p-mc';renderMyClients(p3);root.appendChild(p3);

  // Output panel
  var op=el('div','pb-output-panel');op.id='pb-output-panel';
  var opH=el('div','pb-output-hdr');opH.appendChild(el('h3','','Command Output'));
  var cb=el('span','pb-output-close','\u2715');cb.addEventListener('click',closePanel);opH.appendChild(cb);op.appendChild(opH);
  var opB=el('div','pb-output-body');opB.id='pb-output-body';opB.appendChild(el('div','','No commands run yet.'));op.appendChild(opB);root.appendChild(op);
}

// ── SOP REFERENCE TAB ──
function renderSOP(c){
  c.textContent='';
  c.appendChild(el('div','pb-title','SOP Reference'));
  var sub=el('div','pb-subtitle');
  sub.textContent='Time estimates, priority levels, and step-by-step processes for every monthly deliverable. Use this to set expectations, train new specialists, and audit completion quality.';
  c.appendChild(sub);

  // Summary bar
  var sumBar=el('div','pb-summary');sumBar.id='sop-summary';
  c.appendChild(sumBar);

  // Filter pills
  var filters=el('div','pb-filters');filters.id='sop-filters';
  c.appendChild(filters);

  // Card container
  var cards=el('div','');cards.id='sop-cards';
  c.appendChild(cards);

  updateSOP();
}

function updateSOP(){
  var filtered=curCatFilter==='All'?SOPs:SOPs.filter(function(s){return s.category===curCatFilter;});
  var totalTime=filtered.reduce(function(a,s){return a+Math.round((s.timeMin+s.timeMax)/2);},0);
  var h=Math.floor(totalTime/60),m=totalTime%60;

  // Summary
  var sumBar=document.getElementById('sop-summary');
  if(sumBar){
    sumBar.textContent='';
    var timeItem=el('div','pb-summary-item');
    var clockSpan=el('span','');clockSpan.style.cssText='display:flex;align-items:center;color:var(--pb-primary);';
    clockSpan.insertAdjacentHTML('beforeend',CLOCK);
    timeItem.appendChild(clockSpan);
    timeItem.appendChild(el('span','','\u00A0'+(curCatFilter==='All'?'Full month':'  '+curCatFilter)+' est. time: '));
    timeItem.appendChild(el('span','pb-summary-value',h>0?h+'h'+(m>0?' '+m+'m':''):m+' min'));
    sumBar.appendChild(timeItem);
    sumBar.appendChild(el('div','pb-summary-sep'));
    var countItem=el('div','pb-summary-item');
    countItem.appendChild(el('span','pb-summary-value',String(filtered.length)));
    countItem.appendChild(el('span','','\u00A0deliverable types'));
    sumBar.appendChild(countItem);
    var toggle=el('div','pb-summary-action',(expandAll?'\u25B8 Collapse all':'\u25B8 Expand all'));
    toggle.addEventListener('click',function(){expandAll=!expandAll;updateSOP();});
    sumBar.appendChild(toggle);
  }

  // Filters
  var filtersEl=document.getElementById('sop-filters');
  if(filtersEl){
    filtersEl.textContent='';
    CATEGORIES.forEach(function(cat){
      var btn=el('div','pb-filter'+(cat===curCatFilter?' active':''),cat);
      if(cat!=='All'){
        var count=SOPs.filter(function(s){return s.category===cat;}).length;
        btn.appendChild(el('span','pb-filter-count',String(count)));
      }
      btn.addEventListener('click',function(){curCatFilter=cat;updateSOP();});
      filtersEl.appendChild(btn);
    });
  }

  // Cards
  var cardsEl=document.getElementById('sop-cards');
  if(cardsEl){
    cardsEl.textContent='';
    filtered.forEach(function(task){
      var card=el('div','pb-sop-card'+(expandAll?' open':''));
      var btn=el('button','pb-sop-btn');
      btn.type='button';
      btn.addEventListener('click',function(){card.classList.toggle('open');});

      var left=el('div','pb-sop-left');
      var chips=el('div','pb-sop-chips');
      chips.appendChild(el('span','pb-chip '+(CAT_CHIP[task.category]||''),task.category));
      chips.appendChild(el('span','pb-badge pb-badge-'+task.priority,task.priority.charAt(0).toUpperCase()+task.priority.slice(1)+' Priority'));
      left.appendChild(chips);
      left.appendChild(el('div','pb-sop-title',task.title));
      btn.appendChild(left);

      var right=el('div','pb-sop-right');
      var tp=el('div','pb-time-pill');
      tp.insertAdjacentHTML('beforeend',CLOCK);
      tp.appendChild(el('span','','\u00A0'+fmtTime(task.timeMin,task.timeMax)));
      right.appendChild(tp);
      right.appendChild(el('span','pb-step-count',task.steps.length+' steps'));
      right.appendChild(el('span','pb-chevron',CHEVRON));
      btn.appendChild(right);
      card.appendChild(btn);

      var body=el('div','pb-sop-body');
      var steps=el('div','pb-sop-steps');
      var ol=el('ol','');
      task.steps.forEach(function(step,i){
        var li=el('li','');
        li.appendChild(el('span','pb-step-num',String(i+1)));
        li.appendChild(el('span','pb-step-text',step));
        ol.appendChild(li);
      });
      steps.appendChild(ol);body.appendChild(steps);card.appendChild(body);
      cardsEl.appendChild(card);
    });
  }
}

// ── MONTH CALENDAR TAB ──
function renderCalendar(c){
  c.textContent='';
  c.appendChild(el('div','pb-title','Month Calendar'));
  c.appendChild(el('div','pb-subtitle','Visual distribution of every deliverable across working days, based on the master template.'));

  // Week summary
  var wsum=el('div','pb-week-summary');wsum.id='cal-week-summary';
  c.appendChild(wsum);

  // Calendar
  var calWrap=el('div','pb-cal-wrap');calWrap.id='cal-wrap';
  c.appendChild(calWrap);

  // Legend
  var leg=el('div','pb-legend');leg.id='cal-legend';
  c.appendChild(leg);

  updateCalendar();
}

// Assign SOPs to weeks 1-4
var SOP_WEEKS={};
SOPs.forEach(function(s,i){
  var t=s.title.toLowerCase();
  if(t.indexOf('report')>=0||t.indexOf('heat map')>=0) SOP_WEEKS[i]=4;
  else if(t.indexOf('citation')>=0||t.indexOf('map embed')>=0||t.indexOf('image sharing')>=0) SOP_WEEKS[i]=1;
  else if(t.indexOf('index')>=0) SOP_WEEKS[i]=1;
  else if(t.indexOf('service page')>=0||t.indexOf('blog')>=0||t.indexOf('location page')>=0) SOP_WEEKS[i]=2;
  else if(t.indexOf('gbp')>=0||t.indexOf('google business')>=0||t.indexOf('review')>=0) SOP_WEEKS[i]=1;
  else if(t.indexOf('press release')>=0) SOP_WEEKS[i]=3;
  else if(t.indexOf('pinterest')>=0||t.indexOf('youtube')>=0) SOP_WEEKS[i]=2;
  else if(t.indexOf('patch')>=0||t.indexOf('backlink')>=0||t.indexOf('signal')>=0||t.indexOf('reddit')>=0) SOP_WEEKS[i]=3;
  else SOP_WEEKS[i]=2;
});

function getWorkingDays(y,m){var out=[],d=new Date(y,m,1);while(d.getMonth()===m){var dow=d.getDay();if(dow>=1&&dow<=5)out.push(new Date(d));d.setDate(d.getDate()+1);}return out;}
function isoKey(d){return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}
function getGrid(y,m){var first=new Date(y,m,1);var dow=first.getDay();var back=dow===0?6:dow-1;var start=new Date(y,m,1-back);var days=[];for(var i=0;i<42;i++){days.push(new Date(start.getFullYear(),start.getMonth(),start.getDate()+i));}return days;}

function buildTaskMap(y,m){
  var wd=getWorkingDays(y,m);var map={};
  for(var w=1;w<=4;w++){
    var wdays=wd.slice((w-1)*5,w*5);
    var weekTasks=[];
    SOPs.forEach(function(s,i){if(SOP_WEEKS[i]===w)weekTasks.push(s);});
    weekTasks.forEach(function(task,i){
      var dayIdx=i%Math.max(wdays.length,1);
      var date=wdays[dayIdx];if(!date)return;
      var key=isoKey(date);if(!map[key])map[key]=[];
      map[key].push(task);
    });
  }
  return map;
}

function updateCalendar(){
  // Week summary
  var wsEl=document.getElementById('cal-week-summary');
  if(wsEl){
    wsEl.textContent='';
    for(var w=1;w<=4;w++){
      var weekTasks=SOPs.filter(function(s,i){return SOP_WEEKS[i]===w;});
      var mins=weekTasks.reduce(function(a,s){return a+Math.round((s.timeMin+s.timeMax)/2);},0);
      var card=el('div','pb-ws-card');
      card.appendChild(el('div','pb-ws-label','Week '+w));
      var count=el('div','pb-ws-count',String(weekTasks.length));count.appendChild(el('span','',' tasks'));
      card.appendChild(count);
      var time=el('div','pb-ws-time');time.insertAdjacentHTML('beforeend',CLOCK);time.appendChild(el('span','','\u00A0'+fmtMins(mins)));
      card.appendChild(time);wsEl.appendChild(card);
    }
  }

  // Calendar grid
  var calWrap=document.getElementById('cal-wrap');
  if(!calWrap)return;
  calWrap.textContent='';

  // Nav
  var nav=el('div','pb-cal-nav');
  var prevBtn=el('button','pb-cal-nav-btn','\u25C0');
  prevBtn.addEventListener('click',function(){if(calMonth===0){calYear--;calMonth=11;}else calMonth--;updateCalendar();});
  var nextBtn=el('button','pb-cal-nav-btn','\u25B6');
  nextBtn.addEventListener('click',function(){if(calMonth===11){calYear++;calMonth=0;}else calMonth++;updateCalendar();});
  var monthLabel=el('h2','pb-cal-month',MONTHS[calMonth]+' '+calYear);
  nav.appendChild(prevBtn);nav.appendChild(monthLabel);nav.appendChild(nextBtn);
  calWrap.appendChild(nav);

  // Day labels
  var dayLabels=el('div','pb-cal-days');
  WDAYS.forEach(function(d,i){
    dayLabels.appendChild(el('div','pb-cal-day-label'+(i>=5?' weekend':''),d));
  });
  calWrap.appendChild(dayLabels);

  // Grid
  var grid=getGrid(calYear,calMonth);
  var taskMap=buildTaskMap(calYear,calMonth);
  var workdays=getWorkingDays(calYear,calMonth);
  var today=isoKey(new Date());
  var wkStarts=[];for(var w=0;w<4;w++){var d=workdays[w*5];if(d)wkStarts.push(isoKey(d));}

  var gridEl=el('div','pb-cal-grid');
  grid.forEach(function(day){
    var key=isoKey(day);
    var inMonth=day.getMonth()===calMonth&&day.getFullYear()===calYear;
    var isToday=key===today;
    var dow=day.getDay();
    var isWeekend=dow===0||dow===6;
    var dayTasks=taskMap[key]||[];
    var dayMins=dayTasks.reduce(function(a,s){return a+Math.round((s.timeMin+s.timeMax)/2);},0);
    var isWkStart=wkStarts.indexOf(key)>=0;

    var cell=el('div','pb-cal-cell'+(isWeekend?' weekend':'')+(inMonth?'':' outside')+(isToday?' today':''));

    if(isWkStart&&inMonth){
      cell.appendChild(el('span','pb-cal-wk-badge','Wk '+(wkStarts.indexOf(key)+1)));
    }

    var numDiv=el('div','pb-cal-num',String(day.getDate()));
    cell.appendChild(numDiv);

    var tasksDiv=el('div','');tasksDiv.style.cssText='display:flex;flex-direction:column;gap:1px;flex:1;margin-top:2px;';
    dayTasks.forEach(function(task){
      var chip=el('div','pb-cal-task');
      chip.style.cssText=CAT_CALCHIP[task.category]||'';
      chip.title=task.title+' \u00B7 '+task.category+' \u00B7 '+task.priority+' \u00B7 ~'+Math.round((task.timeMin+task.timeMax)/2)+'m';
      chip.appendChild(el('span','pb-dot pb-dot-'+task.priority));
      chip.appendChild(el('span','',task.title));
      tasksDiv.appendChild(chip);
    });
    cell.appendChild(tasksDiv);

    if(dayMins>0){
      var timeDiv=el('div','pb-cal-time');
      timeDiv.insertAdjacentHTML('beforeend','<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>');
      timeDiv.appendChild(el('span','',fmtMins(dayMins)));
      cell.appendChild(timeDiv);
    }

    gridEl.appendChild(cell);
  });
  calWrap.appendChild(gridEl);

  // Legend
  var leg=document.getElementById('cal-legend');
  if(leg){
    leg.textContent='';
    leg.appendChild(el('span','pb-legend-label','Category'));
    Object.keys(CAT_CALCHIP).forEach(function(cat){
      var item=el('div','pb-legend-item');
      var sw=el('span','pb-legend-swatch');sw.style.cssText=CAT_CALCHIP[cat];
      item.appendChild(sw);item.appendChild(el('span','',cat));
      leg.appendChild(item);
    });
    leg.appendChild(el('span','pb-legend-label','Priority'));
    ['high','medium','low'].forEach(function(p){
      var item=el('div','pb-legend-item');
      item.appendChild(el('span','pb-dot pb-dot-'+p));
      item.appendChild(el('span','',p.charAt(0).toUpperCase()+p.slice(1)));
      leg.appendChild(item);
    });
  }
}

// ── FRAMEWORK TAB ──
function renderFramework(c){
  var intro=el('div','pb-intro');
  intro.appendChild(document.createTextNode('This playbook defines '));
  intro.appendChild(el('strong','','how ProofPilot runs SEO fulfillment each month'));
  intro.appendChild(document.createTextNode('. ClickUp tracks tasks. This teaches you '));
  intro.appendChild(el('strong','','when'));
  intro.appendChild(document.createTextNode(' and '));
  intro.appendChild(el('strong','','why'));
  intro.appendChild(document.createTextNode('.'));
  c.appendChild(intro);

  c.appendChild(el('div','pb-title','The Monthly Rhythm'));
  c.appendChild(el('div','pb-subtitle','Every month follows this 4-week cadence. Each week has a primary focus.'));

  var weekData=[
    {num:'Week 1',title:'Audit + Plan + Kickoff',dates:'1st - 7th',groups:[{cat:'admin',tasks:['Run /audit for each client','Generate /monthly-plan per client','Review last month outsource deliverables']},{cat:'outsource',tasks:['Order citations','Order image geo-tagging','Order map embeds']},{cat:'technical',tasks:['Submit last month URLs to indexer']},{cat:'gbp',tasks:['GBP batch #1: 2/T1, 1/T2-3']},{cat:'content',tasks:['Start Tier 1 content']}]},
    {num:'Week 2',title:'Heavy Content Build',dates:'8th - 14th',groups:[{cat:'content',tasks:['Location pages (3-7/client)','Service sub-pages (2-4/client)','Blog posts (2-4/client)','Begin Tier 2 content']},{cat:'gbp',tasks:['GBP batch #2']},{cat:'offpage',tasks:['Pinterest pins','Patch posts','YouTube video','Press release']},{cat:'admin',tasks:['Run /workload on 10th']}]},
    {num:'Week 3',title:'Complete + Off-Page',dates:'15th - 21st',groups:[{cat:'content',tasks:['Finish Tier 1','Tier 2-3 content','Neighborhood pages']},{cat:'offpage',tasks:['Blog comment backlinks','Niche/local signals']},{cat:'gbp',tasks:['GBP batch #3 + reviews']},{cat:'technical',tasks:['Heat map pull #1']},{cat:'admin',tasks:['Run /workload on 15th']}]},
    {num:'Week 4',title:'Report + Wrap + Prep',dates:'22nd - End',groups:[{cat:'reporting',tasks:['Monthly reports','Client update emails']},{cat:'gbp',tasks:['GBP batch #4']},{cat:'technical',tasks:['Heat map pull #2','Submit new links']},{cat:'outsource',tasks:['Verify citations','Verify images','Verify map embeds']},{cat:'admin',tasks:['Run /wrap-up per client','/workload final check','Preview next month roadmap']}]}
  ];

  var wg=el('div','pb-fw-weeks');
  weekData.forEach(function(w,idx){
    var card=el('div','pb-fw-week'+(idx===0?' open':''));
    var hdr=el('div','pb-fw-hdr');hdr.addEventListener('click',function(){card.classList.toggle('open');});
    var left=el('div','');left.appendChild(el('div','pb-fw-num',w.num));left.appendChild(el('div','pb-fw-title',w.title));left.appendChild(el('div','pb-fw-dates',w.dates));
    hdr.appendChild(left);hdr.appendChild(el('div','pb-fw-toggle',CHEVRON));card.appendChild(hdr);
    var body=el('div','pb-fw-body');var inner=el('div','pb-fw-inner');
    w.groups.forEach(function(g){
      var grp=el('div','pb-fw-group');
      var chipCls=g.cat==='admin'?'pb-chip-technical-seo':g.cat==='outsource'?'pb-chip-link-building':g.cat==='gbp'?'pb-chip-local-seo':g.cat==='offpage'?'pb-chip-link-building':g.cat==='content'?'pb-chip-content':g.cat==='technical'?'pb-chip-technical-seo':g.cat==='reporting'?'pb-chip-reporting':'pb-chip-content';
      grp.appendChild(el('div','pb-chip '+chipCls,g.cat));
      g.tasks.forEach(function(t){grp.appendChild(el('div','pb-fw-item',t));});
      inner.appendChild(grp);
    });
    body.appendChild(inner);card.appendChild(body);wg.appendChild(card);
  });
  c.appendChild(wg);
  c.appendChild(el('div','pb-divider'));

  // Priority
  c.appendChild(el('div','pb-title','Priority Matrix'));
  var pyr=el('div','pb-pyramid');
  [['p1','1','Contractual / Overdue','Promised or past due','#ef4444'],['p2','2','Tier 1 High-Impact','Clear ROI signal','#f59e0b'],['p3','3','Tier 1 Recurring','Standard deliverables','#3b82f6'],['p4','4','Tier 2 Content','Mid-tier work','#94a3b8'],['p5','5','Tier 3 + Admin','Lower-tier','#6b7280']].forEach(function(p){
    var lvl=el('div','pb-plevel pb-'+p[0]);var num=el('div','pb-pnum',p[1]);num.style.background=p[4];lvl.appendChild(num);
    var txt=el('div','');txt.appendChild(el('div','',p[2]));txt.appendChild(el('div','pb-pex',p[3]));lvl.appendChild(txt);pyr.appendChild(lvl);
  });c.appendChild(pyr);
  c.appendChild(el('div','pb-divider'));

  // Decision tree
  var dt=el('div','pb-decision');dt.appendChild(el('h3','','What Should I Work On Next?'));
  [['1','#ef4444','Anything overdue or promised?','Do that first.','#ef4444'],['2','#f59e0b','Tier 1 with unstarted content?','Build that page.','#f59e0b'],['3','#6c7aff','Is it Week 1?','Audits and plans.','#6c7aff'],['4','#fb923c','Is it Week 4?','Reports and wrap-ups.','#fb923c'],['5','#34d399','None of the above?','Next highest-tier client.','#34d399']].forEach(function(d){
    var step=el('div','pb-dstep');var num=el('div','pb-pnum',d[0]);num.style.background=d[1];step.appendChild(num);step.appendChild(el('div','pb-dq',d[2]));var a=el('div','pb-da',d[3]);a.style.color=d[4];step.appendChild(a);dt.appendChild(step);
  });c.appendChild(dt);
  c.appendChild(el('div','pb-divider'));

  // Time allocation
  c.appendChild(el('div','pb-title','Time Allocation by Tier'));
  var tg=el('div','pb-time-grid');
  [['Tier 1','1','10-12','$4K MRR. Full build.','85%','#fbbf24'],['Tier 2','2','6-8','$2K MRR. Standard.','55%','#94a3b8'],['Tier 3','3','3-4','$1K MRR. Lean.','30%','#b87333']].forEach(function(t){
    var card=el('div','pb-time-card');card.appendChild(el('div','pb-tier pb-tier-'+t[1],t[0]));
    var hrs=el('div','pb-time-hrs',t[2]);hrs.appendChild(el('span','',' hrs/mo'));card.appendChild(hrs);
    card.appendChild(el('div','pb-time-desc',t[3]));
    var bar=el('div','pb-time-bar');var fill=el('div','pb-time-fill');fill.style.cssText='width:'+t[4]+';background:'+t[5];bar.appendChild(fill);card.appendChild(bar);
    tg.appendChild(card);
  });c.appendChild(tg);
}

// ── MY CLIENTS TAB ──
function renderMyClients(container){
  container.textContent='';
  container.appendChild(el('div','pb-title','Client Overview'));
  container.appendChild(el('div','pb-subtitle','Filter by manager to see assigned clients, tasks, and next pages.'));
  var pills=el('div','pb-pills');
  ['all','Matthew','Marcos','Jo Paula'].forEach(function(m){
    var pill=el('div','pb-pill'+(m===curFilter?' active':''),m==='all'?'All Clients':m);
    pill.addEventListener('click',function(){curFilter=m;renderMyClients(container);});
    pills.appendChild(pill);
  });container.appendChild(pills);

  // Workload
  var mgrs={};DATA.clients.forEach(function(c){if(!mgrs[c.manager])mgrs[c.manager]={n:0,h:0};mgrs[c.manager].n++;mgrs[c.manager].h+=getTotalHours(c);});
  var wl=el('div','pb-wl-grid');
  Object.keys(mgrs).forEach(function(name){
    var card=el('div','pb-wl-card');card.appendChild(el('div','pb-wl-name',name));
    card.appendChild(el('div','pb-wl-count',mgrs[name].n+' clients'));
    var hrs=el('div','pb-wl-hours',String(Math.round(mgrs[name].h)));hrs.appendChild(el('span','',' hrs/mo'));card.appendChild(hrs);
    wl.appendChild(card);
  });container.appendChild(wl);

  var grid=el('div','pb-clients-grid');
  DATA.clients.filter(function(c){return curFilter==='all'||c.manager===curFilter;})
    .sort(function(a,b){return a.tier-b.tier||b.mrr-a.mrr;})
    .forEach(function(c){
      var hrs=Math.round(getTotalHours(c)*10)/10;
      var card=el('div','pb-client-card');
      var hdr=el('div','pb-cc-hdr');hdr.appendChild(el('span','pb-cc-name',c.name));hdr.appendChild(el('span','pb-tier '+tc(c.tier),'Tier '+c.tier));card.appendChild(hdr);
      var meta=el('div','pb-cc-meta');
      ['$'+c.mrr.toLocaleString()+'/mo',c.cadence,c.location,'~'+hrs+' hrs'].forEach(function(txt){meta.appendChild(el('span','',txt));});
      card.appendChild(meta);
      var td=el('div','pb-cc-tasks');td.appendChild(el('h4','','Monthly Tasks'));
      var ul=el('ul','pb-cc-list');
      Object.keys(c.tasks).forEach(function(cat){
        c.tasks[cat].forEach(function(t){
          if(t.time==='outsource')return;
          ul.appendChild(el('li','c-'+cat,t.task+' '+t.time));
        });
      });
      td.appendChild(ul);card.appendChild(td);
      if(c.nextPages&&c.nextPages.length){
        var rr=el('div','');rr.style.cssText='margin-top:10px;padding-top:10px;border-top:1px solid var(--pb-border);';
        rr.appendChild(el('h4','','Next Pages'));
        c.nextPages.forEach(function(p){rr.appendChild(el('div','',p.url+' '+(p.keyword||'')));});
        card.appendChild(rr);
      }
      grid.appendChild(card);
    });
  container.appendChild(grid);
}
})();
