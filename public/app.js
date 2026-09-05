/**
 * MedPulse Health & Clinical Pharmacy Web Application
 */

const API_BASE = '/api';

class MedPulseApp {
  constructor() {
    this.token = localStorage.getItem('medpulse_token') || null;
    this.clientId = this.getOrCreateClientId();
    this.currentUser = null;
    this.activeTab = 'home';

    this.articles = [];
    this.nursingArticles = [];
    this.pharmacyItems = [];
    this.ratingsData = { ratings: [], summary: {} };
    this.users = [];
    
    this.currentArticle = null;
    this.currentPharmacyItem = null;

    this.articleCategoryFilter = 'All';
    this.pharmacyTypeFilter = 'all';
    this.pharmacyCategoryFilter = 'All';
    this.pharmacySearchTerm = '';
    this.globalSearchTerm = '';

    this.selectedStarScore = 0;

    this.init();
  }

  /* ==================== ANONYMOUS VISITOR IDENTITY ==================== */
  // Persistent per-browser id so a visitor can't like/rate the same thing twice,
  // but can still come back later and edit their own review.
  getOrCreateClientId() {
    let id = localStorage.getItem('medpulse_client_id');
    if (!id) {
      id = (window.crypto && window.crypto.randomUUID)
        ? window.crypto.randomUUID()
        : `client-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      localStorage.setItem('medpulse_client_id', id);
    }
    return id;
  }

  async init() {
    await this.checkAuth();
    await this.loadStats();
    await this.loadArticles();
    await this.loadNursingArticles();
    await this.loadPharmacy();
    await this.loadRatings();
    await this.loadUsers();

    // Check hash for direct navigation
    const hash = window.location.hash.replace('#', '');
    const VALID_TABS = ['home', 'pharmacy', 'nursing', 'pt', 'ot', 'other-health', 'education', 'student-resources', 'articles', 'ratings', 'about'];
    if (VALID_TABS.includes(hash)) {
      this.navigate(hash);
    } else {
      this.navigate('home');
    }

    // Close the "Explore Careers" dropdown when clicking anywhere outside it
    document.addEventListener('click', (e) => {
      document.querySelectorAll('.nav-dropdown[open]').forEach(d => {
        if (!d.contains(e.target)) d.removeAttribute('open');
      });
    });

    if (window.lucide) {
      window.lucide.createIcons();
    }
  }

  /* ==================== TOAST NOTIFICATIONS ==================== */
  showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    const isSuccess = type === 'success';
    const isError = type === 'error';
    
    const bgClass = isSuccess 
      ? 'bg-slate-900 border-blue-500 text-white' 
      : isError 
      ? 'bg-rose-900 border-rose-500 text-white' 
      : 'bg-slate-900 border-slate-700 text-white';

    const icon = isSuccess ? 'check-circle' : isError ? 'alert-circle' : 'info';

    toast.className = `toast-message pointer-events-auto flex items-center space-x-3 px-4 py-3 rounded-md shadow-xl border text-xs font-semibold ${bgClass}`;
    toast.innerHTML = `
      <i data-lucide="${icon}" class="w-4 h-4 text-blue-400 shrink-0"></i>
      <span>${message}</span>
    `;

    container.appendChild(toast);
    if (window.lucide) window.lucide.createIcons();

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  /* ==================== AUTH & ROLES ==================== */
  async checkAuth() {
    if (!this.token) {
      this.currentUser = null;
      this.renderAuthStatus();
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: { 'Authorization': `Bearer ${this.token}` }
      });
      const data = await res.json();
      if (data.authenticated && data.user) {
        this.currentUser = data.user;
      } else {
        this.currentUser = null;
        this.token = null;
        localStorage.removeItem('medpulse_token');
      }
    } catch (e) {
      console.error('Auth verification failed', e);
      this.currentUser = null;
    }

    this.renderAuthStatus();
  }

  renderAuthStatus() {
    const statusContainer = document.getElementById('auth-status-container');
    const authBtnWrapper = document.getElementById('auth-btn-wrapper');
    const editorActions = document.getElementById('editor-action-buttons');
    const adminManageBtn = document.getElementById('admin-manage-staff-btn');
    const quickAssignWrapper = document.getElementById('admin-quick-assign-wrapper');

    if (this.isEditor()) {
      // Logged in as approved doctor/editor
      const roleLabels = {
        admin: 'Chief Medical Admin',
        medical_editor: 'Medical Article Editor',
        pharmacy_editor: 'Medication Editor',
        editor: 'Approved Clinical Editor'
      };
      const roleBadge = roleLabels[this.currentUser.role] || 'Approved Clinical Editor';
      statusContainer.innerHTML = `
        <div class="flex items-center space-x-2">
          <img src="${this.currentUser.avatar || 'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=100'}" class="w-4 h-4 rounded-full object-cover border border-blue-300" />
          <span class="font-bold">${this.currentUser.name}</span>
          <span class="text-blue-300">(${this.currentUser.title})</span>
          <span class="ml-1 px-1.5 py-0.2 rounded text-[10px] font-bold bg-blue-800 text-blue-100">${roleBadge}</span>
        </div>
      `;

      authBtnWrapper.innerHTML = `
        <button onclick="app.logout()" class="text-sm font-semibold text-rose-700 hover:underline whitespace-nowrap">Log Out</button>
      `;

      if (editorActions) {
        editorActions.classList.remove('hidden');
        editorActions.classList.add('flex');
      }

      const newArticleBtn = document.getElementById('nav-new-article-btn');
      if (newArticleBtn) newArticleBtn.classList.toggle('hidden', !this.canEditArticles());

      const newMedicationBtn = document.getElementById('nav-new-medication-btn');
      if (newMedicationBtn) newMedicationBtn.classList.toggle('hidden', !this.canEditPharmacy());

      if (adminManageBtn) {
        if (this.isAdmin()) {
          adminManageBtn.classList.remove('hidden');
        } else {
          adminManageBtn.classList.add('hidden');
        }
      }

      if (quickAssignWrapper) {
        if (this.isAdmin()) {
          quickAssignWrapper.classList.remove('hidden');
        } else {
          quickAssignWrapper.classList.add('hidden');
        }
      }
    } else {
      // Guest / Visitor
      statusContainer.innerHTML = `
        <div class="flex items-center space-x-2 text-blue-200">
          <span>Guest Mode (Read &amp; Comment Access)</span>
        </div>
      `;

      authBtnWrapper.innerHTML = `
        <button onclick="app.openLoginModal()" class="text-sm font-semibold text-slate-600 hover:text-blue-700 whitespace-nowrap">Staff Login</button>
      `;

      if (editorActions) {
        editorActions.classList.remove('flex');
        editorActions.classList.add('hidden');
      }

      if (adminManageBtn) adminManageBtn.classList.add('hidden');
      if (quickAssignWrapper) quickAssignWrapper.classList.add('hidden');
    }

    if (window.lucide) window.lucide.createIcons();
    this.renderArticles();
    this.renderNursingArticles();
    this.renderPharmacy();
    this.renderEditorialBoard();
  }

  isEditor() {
    return this.currentUser && ['editor', 'admin', 'medical_editor', 'pharmacy_editor'].includes(this.currentUser.role);
  }

  isAdmin() {
    return this.currentUser && this.currentUser.role === 'admin';
  }

  // Medical article publishing/editing is limited to admins, medical editors, and the legacy full-access "editor" role.
  canEditArticles() {
    return this.currentUser && ['editor', 'admin', 'medical_editor'].includes(this.currentUser.role);
  }

  // Pharmacy/medication management is limited to admins, pharmacy editors, and the legacy full-access "editor" role.
  canEditPharmacy() {
    return this.currentUser && ['editor', 'admin', 'pharmacy_editor'].includes(this.currentUser.role);
  }

  openLoginModal() {
    const modal = document.getElementById('modal-login');
    const err = document.getElementById('login-error-msg');
    if (err) err.classList.add('hidden');
    modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  closeLoginModal() {
    document.getElementById('modal-login').classList.add('hidden');
  }

  fillDemoAuth(email, pwd) {
    document.getElementById('login-email').value = email;
    document.getElementById('login-password').value = pwd;
  }

  async handleLogin(e) {
    e.preventDefault();
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    const err = document.getElementById('login-error-msg');

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      const data = await res.json();
      if (!res.ok) {
        err.textContent = data.error || 'Authentication failed. Please check credentials.';
        err.classList.remove('hidden');
        return;
      }

      this.token = data.token;
      this.currentUser = data.user;
      localStorage.setItem('medpulse_token', this.token);

      this.closeLoginModal();
      this.renderAuthStatus();
      this.showToast(data.message || 'Logged in successfully as verified editor!');
    } catch (error) {
      console.error(error);
      err.textContent = 'Server connection error during login.';
      err.classList.remove('hidden');
    }
  }

  async logout() {
    if (this.token) {
      try {
        await fetch(`${API_BASE}/auth/logout`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: this.token })
        });
      } catch (e) {
        console.error(e);
      }
    }
    this.token = null;
    this.currentUser = null;
    localStorage.removeItem('medpulse_token');
    this.renderAuthStatus();
    this.showToast('You have been logged out. Switched to visitor mode.');
  }

  /* ==================== NAVIGATION ====================
     Two visually different kinds of nav links share this one function:
     - Top-level links (Home, Education, Student Resources, Health Information, About)
       get an underline-style active state.
     - "Explore Careers" dropdown items (Pharmacy, Nursing, PT, OT, Other) get a
       highlight-style active state instead, since they sit in a dropdown panel. */
  navigate(tab) {
    this.activeTab = tab;
    window.location.hash = tab;

    const ALL_TABS = ['home', 'pharmacy', 'nursing', 'pt', 'ot', 'other-health', 'education', 'student-resources', 'articles', 'ratings', 'about'];
    const DROPDOWN_TABS = ['pharmacy', 'nursing', 'pt', 'ot', 'other-health'];

    const TOP_INACTIVE = 'nav-link text-sm font-semibold text-slate-700 hover:text-blue-700 py-1 border-b-2 border-transparent transition-colors';
    const TOP_ACTIVE = 'nav-link active text-sm font-semibold text-blue-700 border-b-2 border-blue-700 py-1 transition-colors';
    const DROPDOWN_INACTIVE = 'w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-blue-50 hover:text-blue-700 transition-colors';
    const DROPDOWN_ACTIVE = 'w-full text-left px-4 py-2 text-sm font-semibold text-blue-700 bg-blue-50 transition-colors';

    // Hide all sections and reset every nav link to its inactive style
    ALL_TABS.forEach(t => {
      const sec = document.getElementById(`section-${t}`);
      const link = document.getElementById(`nav-${t}`);
      if (sec) sec.classList.add('hidden');
      if (link) {
        link.className = DROPDOWN_TABS.includes(t) ? DROPDOWN_INACTIVE : TOP_INACTIVE;
      }
    });

    // Show the active section and mark its nav link active
    const activeSec = document.getElementById(`section-${tab}`);
    const activeLink = document.getElementById(`nav-${tab}`);
    if (activeSec) activeSec.classList.remove('hidden');
    if (activeLink) {
      activeLink.className = DROPDOWN_TABS.includes(tab) ? DROPDOWN_ACTIVE : TOP_ACTIVE;
    }

    // The "Explore Careers" dropdown trigger itself shows as active when one of its items is
    const careersTrigger = document.getElementById('nav-careers-trigger');
    if (careersTrigger) {
      careersTrigger.classList.toggle('text-blue-700', DROPDOWN_TABS.includes(tab));
      careersTrigger.classList.toggle('font-bold', DROPDOWN_TABS.includes(tab));
    }
    // Close the dropdown after choosing an item from it
    const dropdown = document.querySelector('.nav-dropdown[open]');
    if (dropdown) dropdown.removeAttribute('open');

    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (window.lucide) window.lucide.createIcons();
  }

  /* ==================== MOBILE NAVIGATION ====================
     Below the md breakpoint the full desktop <nav> (and the header's "Rate This Site"
     pill) are hidden by CSS with no other way to reach them - this panel is that
     phone-sized replacement so every section (including Site Ratings) stays reachable. */
  toggleMobileMenu() {
    const panel = document.getElementById('mobile-nav-panel');
    if (panel) panel.classList.toggle('hidden');
  }

  closeMobileMenu() {
    const panel = document.getElementById('mobile-nav-panel');
    if (panel) panel.classList.add('hidden');
  }

  /* ==================== STATS ==================== */
  async loadStats() {
    try {
      const res = await fetch(`${API_BASE}/stats`);
      const stats = await res.json();
      
      const statArticles = document.getElementById('stat-articles');
      const statPharmacy = document.getElementById('stat-pharmacy');
      const statRating = document.getElementById('stat-rating');
      const navRatingBadge = document.getElementById('nav-rating-badge');

      if (statArticles) statArticles.textContent = `${stats.total_articles}+`;
      if (statPharmacy) statPharmacy.textContent = `${stats.total_medications}+`;
      if (statRating) statRating.textContent = `${stats.avg_rating} / 5.0`;
      if (navRatingBadge) navRatingBadge.textContent = `${stats.avg_rating} ★`;
    } catch (e) {
      console.error('Stats loading error', e);
    }
  }

  /* ==================== MEDICAL ARTICLES ==================== */
  async loadArticles() {
    try {
      let url = `${API_BASE}/articles`;
      const params = [];
      if (this.articleCategoryFilter && this.articleCategoryFilter !== 'All') {
        params.push(`category=${encodeURIComponent(this.articleCategoryFilter)}`);
      }
      if (this.globalSearchTerm) {
        params.push(`search=${encodeURIComponent(this.globalSearchTerm)}`);
      }
      if (params.length > 0) {
        url += '?' + params.join('&');
      }

      const res = await fetch(url);
      const data = await res.json();
      this.articles = data.articles || [];
      
      const badge = document.getElementById('article-count-badge');
      if (badge) badge.textContent = `${this.articles.length} Article${this.articles.length === 1 ? '' : 's'}`;

      this.renderArticles();
    } catch (e) {
      console.error('Error loading articles', e);
    }
  }

  filterArticles(category) {
    this.articleCategoryFilter = category;
    
    // Update button states
    document.querySelectorAll('.art-cat-btn').forEach(btn => {
      if (btn.textContent.trim() === category || (category === 'All' && btn.textContent.trim().includes('All'))) {
        btn.className = 'art-cat-btn active px-3.5 py-1.5 rounded-full text-xs font-bold bg-blue-700 text-white shadow-sm transition';
      } else {
        btn.className = 'art-cat-btn px-3.5 py-1.5 rounded-full text-xs font-bold bg-white text-slate-600 hover:bg-slate-100 border border-slate-200 transition';
      }
    });

    this.loadArticles();
  }

  // Shared card markup for both the Healthcare Basics grid and the Nursing grid -
  // both are just differently-filtered views over the same `articles` table.
  articleCardHtml(art) {
    const tags = Array.isArray(art.tags) ? art.tags : [];
    const isEditor = this.canEditArticles();

    return `
      <div class="medical-card bg-white rounded-md border border-slate-200/90 shadow-sm overflow-hidden flex flex-col justify-between group">
        <div>
          <!-- Article Image & Category Badge -->
          <div class="relative h-48 w-full overflow-hidden bg-slate-100">
            <img
              src="${art.cover_image || 'https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&q=80&w=1000'}"
              alt="${art.title}"
              class="w-full h-full object-cover group-hover:scale-105 transition duration-500"
            />
            <div class="absolute top-3.5 left-3.5 flex items-center space-x-1.5">
              <span class="px-3 py-1 rounded-full text-xs font-bold bg-white/95 backdrop-blur text-blue-800 shadow-sm">
                ${art.category}
              </span>
              <span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-900/80 backdrop-blur text-blue-300">
                ${art.reading_time || '5 min read'}
              </span>
            </div>

            <!-- Editor Quick Action Buttons (Protected) -->
            ${isEditor ? `
              <div class="absolute top-3.5 right-3.5 flex items-center space-x-1.5">
                <button onclick="app.openArticleEditorModal(${art.id})" class="p-1.5 rounded-lg bg-white/90 hover:bg-white text-slate-700 hover:text-blue-700 shadow-md transition" title="Edit Article">
                  <i data-lucide="edit-3" class="w-3.5 h-3.5"></i>
                </button>
                <button onclick="app.deleteArticle(${art.id})" class="p-1.5 rounded-lg bg-white/90 hover:bg-white text-slate-700 hover:text-rose-700 shadow-md transition" title="Delete Article">
                  <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                </button>
              </div>
            ` : ''}
          </div>

          <!-- Content Area -->
          <div class="p-6">
            <div class="flex items-center space-x-2 text-xs text-slate-400 mb-2">
              <i data-lucide="eye" class="w-3.5 h-3.5"></i>
              <span>${art.views || 0} views</span>
              <span>•</span>
              <i data-lucide="thumbs-up" class="w-3.5 h-3.5 text-emerald-600"></i>
              <span class="font-medium text-emerald-700">${art.helpful_count || 0} found helpful</span>
            </div>

            <h3 class="font-extrabold text-slate-900 text-lg leading-snug group-hover:text-blue-700 transition line-clamp-2 cursor-pointer" onclick="app.viewArticle(${art.id})">
              ${art.title}
            </h3>

            <p class="text-xs text-slate-500 mt-2.5 line-clamp-2 leading-relaxed">
              ${art.summary}
            </p>

            <!-- Tags -->
            <div class="flex flex-wrap gap-1.5 mt-4">
              ${tags.slice(0, 3).map(t => `<span class="px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 text-[10px] font-semibold">#${t}</span>`).join('')}
            </div>
          </div>
        </div>

        <!-- Card Footer (Author & Read Button) -->
        <div class="px-6 py-4 bg-slate-50/70 border-t border-slate-100 flex items-center justify-between">
          <div class="flex items-center space-x-2.5">
            <div class="w-7 h-7 rounded-full bg-blue-100 text-blue-800 font-bold flex items-center justify-center text-[10px] border border-blue-200">
              MD
            </div>
            <div>
              <div class="text-xs font-bold text-slate-900 leading-tight">${art.author_name}</div>
              <div class="text-[10px] text-slate-400">${art.author_title}</div>
            </div>
          </div>

          <button onclick="app.viewArticle(${art.id})" class="px-3.5 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-sm transition flex items-center space-x-1">
            <span>Read</span>
            <i data-lucide="chevron-right" class="w-3.5 h-3.5"></i>
          </button>
        </div>
      </div>
    `;
  }

  renderArticles() {
    const grid = document.getElementById('articles-grid');
    if (!grid) return;

    if (this.articles.length === 0) {
      const isEditor = this.canEditArticles();
      grid.innerHTML = `
        <div class="col-span-full py-16 px-6 text-center bg-white rounded-md border border-dashed border-slate-300">
          <div class="w-14 h-14 rounded-md bg-blue-50 border border-blue-100 text-blue-600 mx-auto flex items-center justify-center mb-3">
            <i data-lucide="book-plus" class="w-7 h-7"></i>
          </div>
          <h3 class="text-lg font-extrabold text-slate-900">No Healthcare Basics articles published yet</h3>
          <p class="text-xs text-slate-500 mt-1 max-w-md mx-auto">
            ${isEditor
              ? 'This library is clean and ready. Click below to draft and publish your first guide.'
              : 'Our verified clinical editorial team is preparing evidence-based publications. Please check back soon or log in as an editor to publish content.'}
          </p>
          ${isEditor ? `
            <button onclick="app.openArticleEditorModal(null, 'Public Health')" class="mt-4 inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-md shadow-blue-600/20 transition">
              <i data-lucide="plus-circle" class="w-4 h-4"></i>
              <span>Publish Your First Article</span>
            </button>
          ` : `
            <button onclick="app.openLoginModal()" class="mt-4 inline-flex items-center space-x-2 px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs border border-slate-200 transition">
              <i data-lucide="lock" class="w-3.5 h-3.5"></i>
              <span>Doctor / Editor Login</span>
            </button>
          `}
        </div>
      `;
      if (window.lucide) window.lucide.createIcons();
      return;
    }

    grid.innerHTML = this.articles.map(art => this.articleCardHtml(art)).join('');
    if (window.lucide) window.lucide.createIcons();
  }

  /* ==================== NURSING ====================
     Its own tab in the nav, but backed by the same `articles` table/API as Healthcare
     Basics - just always filtered server-side to category=Nursing. */
  async loadNursingArticles() {
    try {
      let url = `${API_BASE}/articles?category=${encodeURIComponent('Nursing')}`;
      if (this.globalSearchTerm) {
        url += `&search=${encodeURIComponent(this.globalSearchTerm)}`;
      }
      const res = await fetch(url);
      const data = await res.json();
      this.nursingArticles = data.articles || [];

      const badge = document.getElementById('nursing-count-badge');
      if (badge) badge.textContent = `${this.nursingArticles.length} Article${this.nursingArticles.length === 1 ? '' : 's'}`;

      this.renderNursingArticles();
    } catch (e) {
      console.error('Error loading nursing articles', e);
    }
  }

  renderNursingArticles() {
    const grid = document.getElementById('nursing-grid');
    if (!grid) return;

    if (this.nursingArticles.length === 0) {
      const isEditor = this.canEditArticles();
      grid.innerHTML = `
        <div class="col-span-full py-16 px-6 text-center bg-white rounded-md border border-dashed border-slate-300">
          <div class="w-14 h-14 rounded-md bg-blue-50 border border-blue-100 text-blue-600 mx-auto flex items-center justify-center mb-3">
            <i data-lucide="stethoscope" class="w-7 h-7"></i>
          </div>
          <h3 class="text-lg font-extrabold text-slate-900">No nursing articles published yet</h3>
          <p class="text-xs text-slate-500 mt-1 max-w-md mx-auto">
            ${isEditor
              ? 'This section is ready for its first nursing-focused guide.'
              : 'Our editorial team is preparing nursing-focused content. Please check back soon.'}
          </p>
          ${isEditor ? `
            <button onclick="app.openArticleEditorModal(null, 'Nursing')" class="mt-4 inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-md shadow-blue-600/20 transition">
              <i data-lucide="plus-circle" class="w-4 h-4"></i>
              <span>Publish Your First Nursing Article</span>
            </button>
          ` : `
            <button onclick="app.openLoginModal()" class="mt-4 inline-flex items-center space-x-2 px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs border border-slate-200 transition">
              <i data-lucide="lock" class="w-3.5 h-3.5"></i>
              <span>Doctor / Editor Login</span>
            </button>
          `}
        </div>
      `;
      if (window.lucide) window.lucide.createIcons();
      return;
    }

    grid.innerHTML = this.nursingArticles.map(art => this.articleCardHtml(art)).join('');
    if (window.lucide) window.lucide.createIcons();
  }

  async viewArticle(id) {
    try {
      const res = await fetch(`${API_BASE}/articles/${id}?client_identifier=${encodeURIComponent(this.clientId)}`, {
        headers: this.token ? { 'Authorization': `Bearer ${this.token}` } : {}
      });
      const art = await res.json();
      this.currentArticle = art;

      // Populate reader modal
      document.getElementById('reader-category-badge').textContent = art.category;
      document.getElementById('reader-reading-time').textContent = art.reading_time || '5 min read';
      document.getElementById('reader-title').textContent = art.title;
      document.getElementById('reader-author-name').textContent = art.author_name;
      document.getElementById('reader-author-title').textContent = art.author_title;
      document.getElementById('reader-summary').textContent = art.summary;
      document.getElementById('reader-date').textContent = `Published on PA-NHCE • ${new Date(art.created_at).toLocaleDateString()}`;
      
      const avatar = document.getElementById('reader-author-avatar');
      if (avatar) avatar.src = "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=300";

      const coverImg = document.getElementById('reader-cover-image');
      if (coverImg) coverImg.src = art.cover_image || 'https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&q=80&w=1000';

      // Parse Markdown Body
      const bodyContainer = document.getElementById('reader-body');
      if (window.marked) {
        bodyContainer.innerHTML = window.marked.parse(art.content);
      } else {
        bodyContainer.innerHTML = `<p>${art.content}</p>`;
      }

      // Votes
      document.getElementById('vote-helpful-count').textContent = art.helpful_count || 0;
      document.getElementById('vote-unhelpful-count').textContent = art.not_helpful_count || 0;
      this.applyArticleVoteState(art.my_vote || null);

      // Check author role inputs for comments
      const nameInput = document.getElementById('comment-author-name');
      const roleInput = document.getElementById('comment-author-role');
      if (this.currentUser) {
        if (nameInput) nameInput.value = this.currentUser.name;
        if (roleInput) roleInput.value = `Verified ${this.currentUser.role.toUpperCase()} (${this.currentUser.title})`;
      } else {
        if (nameInput && !nameInput.value) nameInput.value = '';
        if (roleInput && !roleInput.value) roleInput.value = 'Patient / Visitor';
      }

      // Load comments for this article
      await this.loadComments(art.id, null);

      // Open Modal
      document.getElementById('modal-article-reader').classList.remove('hidden');
      if (window.lucide) window.lucide.createIcons();

      // Refresh articles list to update view count
      this.loadArticles();
    } catch (e) {
      console.error('Error fetching article detail', e);
      this.showToast('Failed to load article details', 'error');
    }
  }

  closeArticleReader() {
    document.getElementById('modal-article-reader').classList.add('hidden');
    this.currentArticle = null;
  }

  // Greys out and disables whichever vote button (if any) this visitor already used on this article.
  applyArticleVoteState(myVote) {
    const helpfulBtn = document.getElementById('vote-helpful-btn');
    const unhelpfulBtn = document.getElementById('vote-unhelpful-btn');
    [helpfulBtn, unhelpfulBtn].forEach(btn => {
      if (!btn) return;
      btn.disabled = !!myVote;
      btn.classList.toggle('opacity-50', !!myVote);
      btn.classList.toggle('cursor-not-allowed', !!myVote);
      btn.classList.remove('ring-2', 'ring-emerald-400', 'ring-rose-400');
    });
    if (myVote === 'helpful' && helpfulBtn) helpfulBtn.classList.add('ring-2', 'ring-emerald-400');
    if (myVote === 'not_helpful' && unhelpfulBtn) unhelpfulBtn.classList.add('ring-2', 'ring-rose-400');
  }

  async voteArticleHelpful(isHelpful) {
    if (!this.currentArticle) return;
    try {
      const res = await fetch(`${API_BASE}/articles/${this.currentArticle.id}/vote`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.token ? { 'Authorization': `Bearer ${this.token}` } : {})
        },
        body: JSON.stringify({ type: isHelpful ? 'helpful' : 'not_helpful', client_identifier: this.clientId })
      });
      const data = await res.json();
      if (!res.ok) {
        this.showToast(data.error || 'You have already submitted feedback for this article.', 'error');
        this.applyArticleVoteState(isHelpful ? 'helpful' : 'not_helpful');
        return;
      }
      if (data.success) {
        if (isHelpful) {
          this.currentArticle.helpful_count = (this.currentArticle.helpful_count || 0) + 1;
          document.getElementById('vote-helpful-count').textContent = this.currentArticle.helpful_count;
          this.showToast('Thank you for rating this clinical guide as helpful!');
        } else {
          this.currentArticle.not_helpful_count = (this.currentArticle.not_helpful_count || 0) + 1;
          document.getElementById('vote-unhelpful-count').textContent = this.currentArticle.not_helpful_count;
          this.showToast('Feedback recorded. Our editorial board will review this guide.');
        }
        this.applyArticleVoteState(isHelpful ? 'helpful' : 'not_helpful');
      }
    } catch (e) {
      console.error(e);
    }
  }

  /* ==================== COMMENTS SYSTEM ==================== */
  async loadComments(articleId, pharmacyId) {
    try {
      let url = `${API_BASE}/comments?`;
      if (articleId) url += `article_id=${articleId}`;
      if (pharmacyId) url += `pharmacy_id=${pharmacyId}`;
      url += `&client_identifier=${encodeURIComponent(this.clientId)}`;

      const res = await fetch(url, {
        headers: this.token ? { 'Authorization': `Bearer ${this.token}` } : {}
      });
      const data = await res.json();
      const comments = data.comments || [];

      const countBadge = document.getElementById('comment-count-badge');
      if (countBadge) countBadge.textContent = `${comments.length} Comment${comments.length === 1 ? '' : 's'}`;

      const list = document.getElementById('article-comments-list');
      if (!list) return;

      if (comments.length === 0) {
        list.innerHTML = `
          <div class="p-6 text-center bg-slate-50 rounded-md border border-slate-200/80 text-slate-500 text-xs">
            No comments yet. Be the first to ask a medical question or share your experience!
          </div>
        `;
        return;
      }

      list.innerHTML = comments.map(c => {
        const isVerifiedDoctor = c.author_role.toLowerCase().includes('doctor') || 
                                 c.author_role.toLowerCase().includes('editor') || 
                                 c.author_role.toLowerCase().includes('pharmac');

        return `
          <div class="p-4 rounded-md ${isVerifiedDoctor ? 'bg-blue-50/50 border border-blue-200' : 'bg-slate-50 border border-slate-200'} space-y-2">
            <div class="flex items-center justify-between">
              <div class="flex items-center space-x-2">
                <div class="w-6 h-6 rounded-full ${isVerifiedDoctor ? 'bg-blue-600 text-white' : 'bg-slate-300 text-slate-700'} flex items-center justify-center text-[10px] font-bold">
                  ${c.author_name.charAt(0)}
                </div>
                <span class="font-bold text-slate-900 text-xs">${c.author_name}</span>
                <span class="text-[10px] px-2 py-0.5 rounded font-semibold ${isVerifiedDoctor ? 'bg-blue-200 text-blue-900' : 'bg-slate-200 text-slate-600'}">
                  ${c.author_role}
                </span>
              </div>
              <span class="text-[10px] text-slate-400">${new Date(c.created_at).toLocaleDateString()}</span>
            </div>
            <p class="text-xs text-slate-700 leading-relaxed pl-8">
              ${c.content}
            </p>
            <div class="flex justify-end items-center space-x-3 pt-1 text-[11px] text-slate-500">
              ${c.liked_by_me ? `
                <span class="flex items-center space-x-1 text-blue-700 font-semibold cursor-default" title="You already marked this as helpful">
                  <i data-lucide="heart" class="w-3.5 h-3.5 fill-blue-600 text-blue-600"></i>
                  <span>${c.likes || 0} Helpful</span>
                </span>
              ` : `
                <button onclick="app.likeComment(${c.id})" class="flex items-center space-x-1 hover:text-blue-700 transition">
                  <i data-lucide="heart" class="w-3.5 h-3.5"></i>
                  <span>${c.likes || 0} Helpful</span>
                </button>
              `}
            </div>
          </div>
        `;
      }).join('');

      if (window.lucide) window.lucide.createIcons();
    } catch (e) {
      console.error(e);
    }
  }

  async submitComment() {
    const name = document.getElementById('comment-author-name').value.trim() || 'Visitor';
    const role = document.getElementById('comment-author-role').value.trim() || 'Patient / Visitor';
    const content = document.getElementById('comment-content').value.trim();

    if (!content) {
      this.showToast('Please type a comment or medical question first.', 'error');
      return;
    }

    if (!this.currentArticle) return;

    try {
      const res = await fetch(`${API_BASE}/comments`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.token ? { 'Authorization': `Bearer ${this.token}` } : {})
        },
        body: JSON.stringify({
          article_id: this.currentArticle.id,
          author_name: name,
          author_role: role,
          content: content
        })
      });

      const data = await res.json();
      if (!res.ok) {
        this.showToast(data.error || 'Failed to post comment', 'error');
        return;
      }

      document.getElementById('comment-content').value = '';
      this.showToast('Your comment was posted successfully!');
      await this.loadComments(this.currentArticle.id, null);
      this.loadStats();
    } catch (e) {
      console.error(e);
      this.showToast('Error submitting comment', 'error');
    }
  }

  async likeComment(commentId) {
    try {
      const res = await fetch(`${API_BASE}/comments/${commentId}/like`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.token ? { 'Authorization': `Bearer ${this.token}` } : {})
        },
        body: JSON.stringify({ client_identifier: this.clientId })
      });
      const data = await res.json();
      if (!res.ok) {
        this.showToast(data.error || 'You have already marked this comment as helpful.', 'error');
      }
      if (this.currentArticle) {
        this.loadComments(this.currentArticle.id, null);
      }
    } catch (e) {
      console.error(e);
    }
  }

  /* ==================== ARTICLE EDITOR (Approved Editors Only) ==================== */
  openArticleEditorModal(artId = null, defaultCategory = 'Public Health') {
    if (!this.canEditArticles()) {
      this.showToast('Editing is restricted to approved medical staff. Please log in.', 'error');
      this.openLoginModal();
      return;
    }

    const modal = document.getElementById('modal-article-editor');
    const headline = document.getElementById('article-editor-headline');
    const idInput = document.getElementById('edit-article-id');

    if (artId) {
      // Articles render into two separate tabs (Healthcare Basics / Nursing) backed by
      // two separate arrays, so the one being edited could be in either.
      const art = this.articles.find(a => a.id === artId) || (this.nursingArticles || []).find(a => a.id === artId);
      if (!art) return;
      headline.textContent = 'Edit Article';
      idInput.value = art.id;
      document.getElementById('edit-article-title').value = art.title;
      document.getElementById('edit-article-category').value = art.category;
      document.getElementById('edit-article-reading-time').value = art.reading_time || '5 min read';
      document.getElementById('edit-article-tags').value = Array.isArray(art.tags) ? art.tags.join(', ') : '';
      document.getElementById('edit-article-cover').value = art.cover_image || '';
      document.getElementById('edit-article-summary').value = art.summary || '';
      document.getElementById('edit-article-content').value = art.content || '';
    } else {
      headline.textContent = defaultCategory === 'Nursing' ? 'Publish New Nursing Article' : 'Publish New Article';
      idInput.value = '';
      document.getElementById('edit-article-title').value = '';
      document.getElementById('edit-article-category').value = defaultCategory;
      document.getElementById('edit-article-reading-time').value = '5 min read';
      document.getElementById('edit-article-tags').value = 'Clinical, Guidelines';
      document.getElementById('edit-article-cover').value = 'https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&q=80&w=1000';
      document.getElementById('edit-article-summary').value = '';
      document.getElementById('edit-article-content').value = '';
    }

    modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  closeArticleEditorModal() {
    document.getElementById('modal-article-editor').classList.add('hidden');
  }

  async saveArticle() {
    if (!this.canEditArticles()) {
      this.showToast('Unauthorized: Only approved editors can modify articles.', 'error');
      return;
    }

    const id = document.getElementById('edit-article-id').value;
    const title = document.getElementById('edit-article-title').value.trim();
    const category = document.getElementById('edit-article-category').value;
    const readingTime = document.getElementById('edit-article-reading-time').value.trim();
    const tags = document.getElementById('edit-article-tags').value.split(',').map(t => t.trim()).filter(Boolean);
    const cover = document.getElementById('edit-article-cover').value.trim();
    const summary = document.getElementById('edit-article-summary').value.trim();
    const content = document.getElementById('edit-article-content').value.trim();

    if (!title || !content || !summary) {
      this.showToast('Please fill in title, summary, and content.', 'error');
      return;
    }

    const payload = {
      title, category, reading_time: readingTime, tags,
      cover_image: cover, summary, content, specialty_badge: category
    };

    try {
      const url = id ? `${API_BASE}/articles/${id}` : `${API_BASE}/articles`;
      const method = id ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method: method,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.token}`
        },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok) {
        this.showToast(data.error || 'Failed to save medical article', 'error');
        return;
      }

      this.closeArticleEditorModal();
      this.showToast(id ? 'Article updated successfully!' : 'New article published!');
      // Category can move an article between the Nursing and Healthcare Basics tabs, so refresh both.
      await this.loadArticles();
      await this.loadNursingArticles();
      this.loadStats();
    } catch (e) {
      console.error(e);
      this.showToast('Error saving article', 'error');
    }
  }

  async deleteArticle(id) {
    if (!this.canEditArticles()) {
      this.showToast('Only approved editors can delete content.', 'error');
      return;
    }

    if (!confirm('Are you sure you want to remove this article?')) return;

    try {
      const res = await fetch(`${API_BASE}/articles/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${this.token}` }
      });

      const data = await res.json();
      if (!res.ok) {
        this.showToast(data.error || 'Failed to delete article', 'error');
        return;
      }

      this.showToast('Article deleted.');
      await this.loadArticles();
      await this.loadNursingArticles();
      this.loadStats();
    } catch (e) {
      console.error(e);
      this.showToast('Error deleting article', 'error');
    }
  }

  /* ==================== PHARMACY SECTION ==================== */
  async loadPharmacy() {
    try {
      let url = `${API_BASE}/pharmacy`;
      const params = [];
      if (this.pharmacyTypeFilter && this.pharmacyTypeFilter !== 'all') {
        params.push(`type=${encodeURIComponent(this.pharmacyTypeFilter)}`);
      }
      if (this.pharmacyCategoryFilter && this.pharmacyCategoryFilter !== 'All') {
        params.push(`category=${encodeURIComponent(this.pharmacyCategoryFilter)}`);
      }
      if (this.pharmacySearchTerm) {
        params.push(`search=${encodeURIComponent(this.pharmacySearchTerm)}`);
      }

      if (params.length > 0) {
        url += '?' + params.join('&');
      }

      const res = await fetch(url);
      const data = await res.json();
      this.pharmacyItems = data.medications || [];
      this.renderPharmacy();
    } catch (e) {
      console.error('Error loading pharmacy', e);
    }
  }

  filterPharmacyType(type) {
    this.pharmacyTypeFilter = type;
    document.querySelectorAll('.pharm-type-btn').forEach(b => {
      b.className = 'pharm-type-btn px-3.5 py-1.5 rounded-lg text-xs font-bold text-slate-600 hover:text-slate-900';
    });
    const activeBtn = document.getElementById(`pharm-type-${type}`);
    if (activeBtn) {
      activeBtn.className = 'pharm-type-btn active px-3.5 py-1.5 rounded-lg text-xs font-bold bg-white text-slate-900 shadow-sm';
    }
    this.loadPharmacy();
  }

  filterPharmacyCategory(cat) {
    this.pharmacyCategoryFilter = cat;
    this.loadPharmacy();
  }

  filterPharmacySearch(term) {
    this.pharmacySearchTerm = term.trim();
    this.loadPharmacy();
  }

  renderPharmacy() {
    const grid = document.getElementById('pharmacy-grid');
    if (!grid) return;

    if (this.pharmacyItems.length === 0) {
      const isEditor = this.canEditPharmacy();
      grid.innerHTML = `
        <div class="col-span-full py-16 px-6 text-center bg-white rounded-md border border-dashed border-slate-300">
          <div class="w-14 h-14 rounded-md bg-blue-50 border border-blue-100 text-blue-600 mx-auto flex items-center justify-center mb-3">
            <i data-lucide="pill" class="w-7 h-7"></i>
          </div>
          <h3 class="text-lg font-extrabold text-slate-900">No medications in pharmacy directory yet</h3>
          <p class="text-xs text-slate-500 mt-1 max-w-md mx-auto">
            ${isEditor 
              ? 'Your pharmacy catalog is clean and ready. Add OTC and Prescription medications with clinical dosing guidelines, indications, and pricing.' 
              : 'Our clinical pharmacy team is updating the drug directory with clinical monographs. Please check back soon.'}
          </p>
          ${isEditor ? `
            <button onclick="app.openPharmacyEditorModal()" class="mt-4 inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-md shadow-blue-600/20 transition">
              <i data-lucide="plus" class="w-4 h-4"></i>
              <span>Add Your First Medication</span>
            </button>
          ` : ''}
        </div>
      `;
      if (window.lucide) window.lucide.createIcons();
      return;
    }

    const isEditor = this.canEditPharmacy();

    grid.innerHTML = this.pharmacyItems.map(item => {
      const isRx = item.prescription_required === 1;

      return `
        <div class="medical-card bg-white rounded-md border border-slate-200/90 shadow-sm overflow-hidden flex flex-col justify-between p-5">
          <div>
            <!-- Header Badge & Status -->
            <div class="flex items-center justify-between mb-3">
              <span class="px-2.5 py-1 rounded-full text-[10px] font-bold ${isRx ? 'bg-rose-100 text-rose-800 border border-rose-200' : 'bg-emerald-100 text-emerald-800 border border-emerald-200'}">
                ${isRx ? 'Rx Required (Prescription)' : 'OTC (Over-The-Counter)'}
              </span>
              <span class="text-xs font-bold text-amber-500 flex items-center space-x-1">
                <i data-lucide="star" class="w-3.5 h-3.5 fill-amber-400 text-amber-400"></i>
                <span>${item.rating || 4.9}</span>
              </span>
            </div>

            <!-- Medication Title -->
            <h3 class="font-black text-slate-900 text-base leading-snug cursor-pointer hover:text-blue-700 transition" onclick="app.viewPharmacyDetail(${item.id})">
              ${item.name}
            </h3>
            <p class="text-[11px] text-slate-500 font-medium mt-0.5">
              Generic: <strong class="text-slate-700">${item.generic_name}</strong>
            </p>

            <div class="my-3 py-2 px-3 bg-slate-50 rounded-xl border border-slate-100 flex items-center justify-between text-xs">
              <span class="text-slate-500 text-[11px] font-medium">${item.dosage_form}</span>
              <span class="text-blue-700 font-extrabold">$${parseFloat(item.price).toFixed(2)}</span>
            </div>

            <p class="text-xs text-slate-600 line-clamp-2 leading-relaxed mb-4">
              ${item.indications}
            </p>
          </div>

          <!-- Actions -->
          <div class="pt-3 border-t border-slate-100 space-y-2">
            <button onclick="app.viewPharmacyDetail(${item.id})" class="w-full py-2 px-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs shadow-sm transition flex items-center justify-center space-x-1.5">
              <i data-lucide="info" class="w-3.5 h-3.5"></i>
              <span>Dosage & Safety Guide</span>
            </button>

            ${isEditor ? `
              <div class="flex items-center space-x-2 pt-1">
                <button onclick="app.openPharmacyEditorModal(${item.id})" class="w-1/2 py-1.5 rounded-lg border border-blue-200 text-blue-800 text-[11px] font-bold hover:bg-blue-50 transition flex items-center justify-center space-x-1">
                  <i data-lucide="edit-3" class="w-3 h-3"></i>
                  <span>Edit</span>
                </button>
                <button onclick="app.deletePharmacyItem(${item.id})" class="w-1/2 py-1.5 rounded-lg border border-rose-200 text-rose-800 text-[11px] font-bold hover:bg-rose-50 transition flex items-center justify-center space-x-1">
                  <i data-lucide="trash-2" class="w-3 h-3"></i>
                  <span>Delete</span>
                </button>
              </div>
            ` : ''}
          </div>
        </div>
      `;
    }).join('');

    if (window.lucide) window.lucide.createIcons();
  }

  viewPharmacyDetail(id) {
    const item = this.pharmacyItems.find(p => p.id === id);
    if (!item) return;

    this.currentPharmacyItem = item;
    const isRx = item.prescription_required === 1;

    const badge = document.getElementById('pharm-modal-badge');
    badge.className = `px-3 py-0.5 rounded-full text-xs font-bold ${isRx ? 'bg-rose-100 text-rose-800' : 'bg-emerald-100 text-emerald-800'}`;
    badge.textContent = isRx ? 'Prescription Required (Rx Only)' : 'Over-The-Counter (OTC Medication)';

    document.getElementById('pharm-modal-name').textContent = item.name;
    document.getElementById('pharm-modal-generic').textContent = `Active Substance: ${item.generic_name} • Category: ${item.category}`;
    document.getElementById('pharm-modal-dosage').textContent = item.dosage_form;
    document.getElementById('pharm-modal-price').textContent = `$${parseFloat(item.price).toFixed(2)}`;
    document.getElementById('pharm-modal-indications').textContent = item.indications;
    document.getElementById('pharm-modal-usage').textContent = item.usage_instructions;
    document.getElementById('pharm-modal-side-effects').textContent = item.side_effects || 'None reported for standard dosing.';
    document.getElementById('pharm-modal-contraindications').textContent = item.contraindications || 'None specified.';
    document.getElementById('pharm-modal-storage').textContent = item.storage_info;

    document.getElementById('modal-pharmacy-detail').classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  closePharmacyDetail() {
    document.getElementById('modal-pharmacy-detail').classList.add('hidden');
    this.currentPharmacyItem = null;
  }

  openPharmacyEditorModal(id = null) {
    if (!this.canEditPharmacy()) {
      this.showToast('Pharmacy management requires approved editor login.', 'error');
      this.openLoginModal();
      return;
    }

    const modal = document.getElementById('modal-pharmacy-editor');
    const headline = document.getElementById('pharmacy-editor-headline');
    const idInput = document.getElementById('edit-pharm-id');

    if (id) {
      const item = this.pharmacyItems.find(p => p.id === id);
      if (!item) return;
      headline.textContent = 'Edit Pharmacy Medication';
      idInput.value = item.id;
      document.getElementById('edit-pharm-name').value = item.name;
      document.getElementById('edit-pharm-generic').value = item.generic_name;
      document.getElementById('edit-pharm-category').value = item.category;
      document.getElementById('edit-pharm-dosage').value = item.dosage_form;
      document.getElementById('edit-pharm-price').value = item.price;
      document.getElementById('edit-pharm-rx').checked = item.prescription_required === 1;
      document.getElementById('edit-pharm-indications').value = item.indications;
      document.getElementById('edit-pharm-usage').value = item.usage_instructions;
      document.getElementById('edit-pharm-side-effects').value = item.side_effects || '';
      document.getElementById('edit-pharm-contraindications').value = item.contraindications || '';
      document.getElementById('edit-pharm-storage').value = item.storage_info || 'Store at room temperature.';
    } else {
      headline.textContent = 'Add Pharmacy Medication';
      idInput.value = '';
      document.getElementById('edit-pharm-name').value = '';
      document.getElementById('edit-pharm-generic').value = '';
      document.getElementById('edit-pharm-category').value = 'Antibiotics';
      document.getElementById('edit-pharm-dosage').value = '500mg Tablet';
      document.getElementById('edit-pharm-price').value = '15.00';
      document.getElementById('edit-pharm-rx').checked = false;
      document.getElementById('edit-pharm-indications').value = '';
      document.getElementById('edit-pharm-usage').value = '';
      document.getElementById('edit-pharm-side-effects').value = '';
      document.getElementById('edit-pharm-contraindications').value = '';
      document.getElementById('edit-pharm-storage').value = 'Store at room temperature 20°C to 25°C.';
    }

    modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  closePharmacyEditorModal() {
    document.getElementById('modal-pharmacy-editor').classList.add('hidden');
  }

  async savePharmacyItem() {
    if (!this.canEditPharmacy()) {
      this.showToast('Unauthorized: Only approved editors can modify medications.', 'error');
      return;
    }

    const id = document.getElementById('edit-pharm-id').value;
    const name = document.getElementById('edit-pharm-name').value.trim();
    const generic = document.getElementById('edit-pharm-generic').value.trim();
    const category = document.getElementById('edit-pharm-category').value;
    const dosage = document.getElementById('edit-pharm-dosage').value.trim();
    const price = parseFloat(document.getElementById('edit-pharm-price').value || 10);
    const rx = document.getElementById('edit-pharm-rx').checked;
    const indications = document.getElementById('edit-pharm-indications').value.trim();
    const usage = document.getElementById('edit-pharm-usage').value.trim();
    const sideEffects = document.getElementById('edit-pharm-side-effects').value.trim();
    const contra = document.getElementById('edit-pharm-contraindications').value.trim();
    const storage = document.getElementById('edit-pharm-storage').value.trim();

    if (!name || !indications || !usage) {
      this.showToast('Please fill in medication name, indications, and usage instructions.', 'error');
      return;
    }

    const payload = {
      name, generic_name: generic, category, dosage_form: dosage,
      price, prescription_required: rx ? 1 : 0, indications,
      usage_instructions: usage, side_effects: sideEffects,
      contraindications: contra, storage_info: storage
    };

    try {
      const url = id ? `${API_BASE}/pharmacy/${id}` : `${API_BASE}/pharmacy`;
      const method = id ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method: method,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.token}`
        },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok) {
        this.showToast(data.error || 'Failed to save medication', 'error');
        return;
      }

      this.closePharmacyEditorModal();
      this.showToast(id ? 'Medication updated in pharmacy catalog.' : 'New medication added to pharmacy!');
      await this.loadPharmacy();
      this.loadStats();
    } catch (e) {
      console.error(e);
      this.showToast('Error saving pharmacy item', 'error');
    }
  }

  async deletePharmacyItem(id) {
    if (!this.canEditPharmacy()) {
      this.showToast('Only approved editors can delete pharmacy listings.', 'error');
      return;
    }

    if (!confirm('Are you sure you want to remove this medication from the pharmacy directory?')) return;

    try {
      const res = await fetch(`${API_BASE}/pharmacy/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${this.token}` }
      });

      const data = await res.json();
      if (!res.ok) {
        this.showToast(data.error || 'Failed to delete medication', 'error');
        return;
      }

      this.showToast('Medication removed from catalog.');
      await this.loadPharmacy();
      this.loadStats();
    } catch (e) {
      console.error(e);
      this.showToast('Error deleting medication', 'error');
    }
  }

  openPrescriptionInquiryModal() {
    document.getElementById('modal-rx-inquiry').classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  closePrescriptionInquiryModal() {
    document.getElementById('modal-rx-inquiry').classList.add('hidden');
  }

  submitPrescriptionInquiry() {
    const name = document.getElementById('rx-patient-name').value.trim();
    const med = document.getElementById('rx-med-name').value.trim();
    if (!name || !med) {
      this.showToast('Please provide your name and the required medication.', 'error');
      return;
    }

    this.closePrescriptionInquiryModal();
    document.getElementById('rx-patient-name').value = '';
    document.getElementById('rx-med-name').value = '';
    document.getElementById('rx-doctor-ref').value = '';
    document.getElementById('rx-notes').value = '';
    this.showToast('Prescription consultation request received! Our clinical pharmacy team will review it.');
  }

  /* ==================== SITE RATINGS & FEEDBACK ==================== */
  async loadRatings() {
    try {
      const res = await fetch(`${API_BASE}/ratings`);
      const data = await res.json();
      this.ratingsData = data;
      this.renderRatings();
    } catch (e) {
      console.error('Error loading ratings', e);
    }
  }

  renderRatings() {
    const summary = this.ratingsData.summary || {};
    const ratings = this.ratingsData.ratings || [];

    const avg = summary.average || 4.9;
    const total = summary.total || ratings.length;
    const dist = summary.distribution || { 1:0, 2:0, 3:0, 4:0, 5:0 };

    const bigScore = document.getElementById('rating-big-score');
    if (bigScore) bigScore.textContent = avg.toFixed(1);

    const totalLabel = document.getElementById('rating-total-label');
    if (totalLabel) totalLabel.textContent = `Based on ${total} verified community review${total === 1 ? '' : 's'}`;

    const starsBox = document.getElementById('rating-big-stars');
    if (starsBox) {
      let starsHtml = '';
      for (let i = 1; i <= 5; i++) {
        starsHtml += `<span class="text-xl">${i <= Math.round(avg) ? '★' : '☆'}</span>`;
      }
      starsBox.innerHTML = starsHtml;
    }

    // Distribution Bars
    for (let s = 1; s <= 5; s++) {
      const count = dist[s] || 0;
      const pct = total > 0 ? Math.round((count / total) * 100) : 0;
      const bar = document.getElementById(`bar-${s}-star`);
      const countLabel = document.getElementById(`count-${s}-star`);
      if (bar) bar.style.width = `${pct}%`;
      if (countLabel) countLabel.textContent = count;
    }

    // Reviews Wall
    const grid = document.getElementById('ratings-reviews-grid');
    if (!grid) return;

    if (ratings.length === 0) {
      grid.innerHTML = `<div class="col-span-full py-8 text-center text-slate-400 text-xs">No ratings submitted yet. Be the first to rate PA-NHCE!</div>`;
      return;
    }

    grid.innerHTML = ratings.map(r => {
      let stars = '';
      for (let i = 1; i <= 5; i++) {
        stars += `<span class="${i <= r.score ? 'text-amber-400' : 'text-slate-300'}">★</span>`;
      }

      return `
        <div class="bg-white p-5 rounded-md border border-slate-200 shadow-sm flex flex-col justify-between space-y-3">
          <div>
            <div class="flex items-center justify-between">
              <div class="text-sm font-bold text-slate-900">${stars}</div>
              <div class="flex items-center space-x-1.5">
                <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-800 border border-blue-100">
                  ${r.category || 'Overall Experience'}
                </span>
                ${this.isAdmin() ? `
                  <button onclick="app.deleteRating(${r.id})" class="p-1 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition" title="Delete this review (Full Administrator)">
                    <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                  </button>
                ` : ''}
              </div>
            </div>
            <p class="text-xs text-slate-600 mt-2.5 leading-relaxed italic">
              "${r.feedback || 'Excellent clinical portal with accurate information.'}"
            </p>
          </div>

          <div class="flex items-center justify-between pt-2 border-t border-slate-100 text-[11px]">
            <div class="font-bold text-slate-800 flex items-center space-x-1">
              <i data-lucide="user" class="w-3.5 h-3.5 text-blue-600"></i>
              <span>${r.user_name}</span>
            </div>
            <span class="text-[10px] text-slate-400">${new Date(r.created_at).toLocaleDateString()}</span>
          </div>
        </div>
      `;
    }).join('');

    if (window.lucide) window.lucide.createIcons();
  }

  async openSiteRatingModal() {
    // Reset to a blank, unselected state first (no rating is pre-picked for you).
    this.selectStarRating(0);
    document.getElementById('rating-user-name').value = '';
    document.getElementById('rating-category').value = 'Overall Experience';
    document.getElementById('rating-feedback').value = '';
    document.getElementById('rating-recommend').checked = true;
    document.getElementById('site-rating-headline').textContent = 'Rate PA-NHCE';
    document.getElementById('site-rating-submit-btn').textContent = 'Submit Review';

    document.getElementById('modal-site-rating').classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();

    // A visitor can only ever have one review - if they already left one, load it so
    // re-submitting edits that review in place instead of creating a duplicate.
    try {
      const headers = this.token ? { 'Authorization': `Bearer ${this.token}` } : {};
      const res = await fetch(`${API_BASE}/ratings/my?client_identifier=${encodeURIComponent(this.clientId)}`, { headers });
      const data = await res.json();
      if (data.review) {
        this.selectStarRating(data.review.score);
        document.getElementById('rating-user-name').value = data.review.user_name || '';
        document.getElementById('rating-category').value = data.review.category || 'Overall Experience';
        document.getElementById('rating-feedback').value = data.review.feedback || '';
        document.getElementById('rating-recommend').checked = !!data.review.recommended;
        document.getElementById('site-rating-headline').textContent = 'Update Your Review';
        document.getElementById('site-rating-submit-btn').textContent = 'Update Review';
      }
    } catch (e) {
      console.error('Error loading existing review', e);
    }
  }

  closeSiteRatingModal() {
    document.getElementById('modal-site-rating').classList.add('hidden');
  }

  selectStarRating(score) {
    this.selectedStarScore = score;
    const stars = document.querySelectorAll('#star-selector .star-btn');
    stars.forEach((s, idx) => {
      if (idx < score) {
        s.classList.remove('inactive');
      } else {
        s.classList.add('inactive');
      }
    });

    const labels = {
      0: 'Select a rating',
      1: '1 Star (Poor)',
      2: '2 Stars (Fair)',
      3: '3 Stars (Good)',
      4: '4 Stars (Very Good)',
      5: '5 Stars (Excellent)'
    };
    document.getElementById('star-selected-label').textContent = labels[score] || `${score} Stars`;
  }

  async submitSiteRating() {
    if (!this.selectedStarScore || this.selectedStarScore < 1) {
      this.showToast('Please select a star rating before submitting.', 'error');
      return;
    }

    const name = document.getElementById('rating-user-name').value.trim() || 'Community Member';
    const category = document.getElementById('rating-category').value;
    const feedback = document.getElementById('rating-feedback').value.trim();
    const recommend = document.getElementById('rating-recommend').checked;

    try {
      const res = await fetch(`${API_BASE}/ratings`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.token ? { 'Authorization': `Bearer ${this.token}` } : {})
        },
        body: JSON.stringify({
          score: this.selectedStarScore,
          user_name: name,
          category: category,
          feedback: feedback,
          recommended: recommend,
          client_identifier: this.clientId
        })
      });

      const data = await res.json();
      if (!res.ok) {
        this.showToast(data.error || 'Failed to submit rating', 'error');
        return;
      }

      this.closeSiteRatingModal();
      document.getElementById('rating-user-name').value = '';
      document.getElementById('rating-feedback').value = '';
      this.showToast(data.message || 'Thank you for your rating!');
      await this.loadRatings();
      await this.loadStats();
    } catch (e) {
      console.error(e);
      this.showToast('Error submitting rating', 'error');
    }
  }

  async deleteRating(ratingId) {
    if (!this.isAdmin()) {
      this.showToast('Only Full Administrators can delete a review.', 'error');
      return;
    }

    if (!confirm('Delete this review? This cannot be undone.')) return;

    try {
      const res = await fetch(`${API_BASE}/ratings/${ratingId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${this.token}` }
      });
      const data = await res.json();
      if (!res.ok) {
        this.showToast(data.error || 'Failed to delete review', 'error');
        return;
      }

      this.showToast('Review deleted.');
      await this.loadRatings();
      await this.loadStats();
    } catch (e) {
      console.error(e);
      this.showToast('Error deleting review', 'error');
    }
  }

  /* ==================== GLOBAL SEARCH ==================== */
  handleGlobalSearch(val) {
    this.globalSearchTerm = val.trim();
  }

  executeSearch() {
    if (this.globalSearchTerm) {
      this.navigate('articles');
      this.loadArticles();
      this.loadNursingArticles();
      this.pharmacySearchTerm = this.globalSearchTerm;
      const pInput = document.getElementById('pharmacy-search-input');
      if (pInput) pInput.value = this.globalSearchTerm;
      this.loadPharmacy();
    }
  }

  /* ==================== USER & EDITOR MANAGEMENT ==================== */
  async loadUsers() {
    try {
      const res = await fetch(`${API_BASE}/users`);
      const data = await res.json();
      this.users = data.users || [];
      this.renderEditorialBoard();
      this.renderUserManagementTable();
    } catch (e) {
      console.error('Failed to load editorial staff', e);
    }
  }

  // Small pill describing an account's actual module access, used in both the public
  // editorial board and the admin's staff management table.
  roleBadgeHtml(role, size = 'normal') {
    const sizeClass = size === 'small'
      ? 'px-2 py-0.5 rounded-full text-[10px] font-bold'
      : 'px-2 py-0.5 rounded-full text-[10px] font-extrabold border';
    const styles = {
      admin: `bg-indigo-100 text-indigo-800 border-indigo-200 ${sizeClass}`,
      medical_editor: `bg-blue-100 text-blue-800 border-blue-200 ${sizeClass}`,
      pharmacy_editor: `bg-emerald-100 text-emerald-800 border-emerald-200 ${sizeClass}`,
      editor: `bg-slate-100 text-slate-800 border-slate-200 ${sizeClass}`
    };
    const labels = {
      admin: 'Full Administrator',
      medical_editor: 'Medical Article Editor',
      pharmacy_editor: 'Medication Editor',
      editor: 'Clinical Editor (Full)'
    };
    const cls = styles[role] || styles.editor;
    const label = labels[role] || 'Clinical Editor';
    return `<span class="inline-flex items-center ${cls}">${label}</span>`;
  }

  renderEditorialBoard() {
    const grid = document.getElementById('editorial-board-grid');
    if (!grid) return;

    if (!this.users || this.users.length === 0) {
      grid.innerHTML = `<div class="col-span-full py-6 text-center text-slate-400 text-xs">No editorial staff listed.</div>`;
      return;
    }

    grid.innerHTML = this.users.map(u => {
      const roleBadge = this.roleBadgeHtml(u.role);

      return `
        <div class="p-4 rounded-md bg-slate-50 border border-slate-200 flex items-start space-x-3.5 hover:border-blue-300 transition">
          <img src="${u.avatar || 'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=300'}" alt="${u.name}" class="w-12 h-12 rounded-md object-cover border border-slate-200 shadow-sm shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between gap-1 flex-wrap">
              <h4 class="font-extrabold text-slate-900 text-sm truncate">${u.name}</h4>
              ${roleBadge}
            </div>
            <p class="text-xs text-slate-600 font-medium mt-0.5">${u.title}</p>
            <div class="flex items-center space-x-2 text-[11px] text-slate-400 mt-2">
              <span class="truncate">${u.email}</span>
              <span>•</span>
              <span class="text-emerald-700 font-semibold flex items-center space-x-1">
                <i data-lucide="check-circle-2" class="w-3 h-3"></i>
                <span>Verified Clinician</span>
              </span>
            </div>
          </div>
        </div>
      `;
    }).join('');

    if (window.lucide) window.lucide.createIcons();
  }

  renderUserManagementTable() {
    const tbody = document.getElementById('user-management-table-body');
    const countLabel = document.getElementById('user-management-count');
    if (!tbody) return;

    if (countLabel) {
      countLabel.textContent = `${this.users.length} Approved Staff Member${this.users.length === 1 ? '' : 's'}`;
    }

    if (!this.users || this.users.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="py-8 text-center text-slate-400">No staff members found.</td></tr>`;
      return;
    }

    tbody.innerHTML = this.users.map(u => {
      const isSelf = this.currentUser && this.currentUser.id === u.id;
      const roleBadge = this.roleBadgeHtml(u.role, 'small');

      return `
        <tr class="hover:bg-slate-50/80 transition">
          <td class="py-3.5 px-4">
            <div class="flex items-center space-x-3">
              <img src="${u.avatar || 'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=300'}" class="w-9 h-9 rounded-xl object-cover border border-slate-200" />
              <div>
                <div class="font-bold text-slate-900">${u.name} ${isSelf ? '<span class="text-[10px] font-normal text-blue-600">(You)</span>' : ''}</div>
                <div class="text-[11px] text-slate-400">Joined ${u.created_at ? u.created_at.split(' ')[0] : '2026'}</div>
              </div>
            </div>
          </td>
          <td class="py-3.5 px-4 font-medium text-slate-700">
            ${u.title}
          </td>
          <td class="py-3.5 px-4">
            ${roleBadge}
          </td>
          <td class="py-3.5 px-4 font-mono text-[11px] text-slate-500">
            ${u.email}
          </td>
          <td class="py-3.5 px-4 text-right">
            <div class="flex items-center justify-end space-x-1.5">
              <button onclick="app.openEditUserModal(${u.id})" class="p-1.5 rounded-lg text-slate-600 hover:text-blue-700 hover:bg-slate-100 transition" title="Edit Staff Details">
                <i data-lucide="edit-3" class="w-4 h-4"></i>
              </button>
              ${isSelf ? `
                <span class="p-1.5 text-slate-300 cursor-not-allowed" title="Cannot delete active account">
                  <i data-lucide="trash-2" class="w-4 h-4"></i>
                </span>
              ` : `
                <button onclick="app.deleteUser(${u.id}, '${u.name.replace(/'/g, "\\'")}')" class="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition" title="Revoke Access">
                  <i data-lucide="trash-2" class="w-4 h-4"></i>
                </button>
              `}
            </div>
          </td>
        </tr>
      `;
    }).join('');

    if (window.lucide) window.lucide.createIcons();
  }

  openUserManagementModal() {
    if (!this.isAdmin()) {
      this.showToast('You must be logged in as an administrator to manage staff.', 'error');
      return;
    }
    const modal = document.getElementById('modal-user-management');
    if (modal) {
      modal.classList.remove('hidden');
      this.loadUsers();
      if (window.lucide) window.lucide.createIcons();
    }
  }

  closeUserManagementModal() {
    const modal = document.getElementById('modal-user-management');
    if (modal) modal.classList.add('hidden');
  }

  openAssignUserModal() {
    document.getElementById('user-form-headline').textContent = 'Assign Medical Editor';
    document.getElementById('user-form-submit-btn').textContent = 'Assign & Save Permissions';
    document.getElementById('user-form-id').value = '';
    document.getElementById('user-form-name').value = '';
    document.getElementById('user-form-email').value = '';
    document.getElementById('user-form-title').value = '';
    document.getElementById('user-form-role').value = 'editor';
    document.getElementById('user-form-password').value = '';
    document.getElementById('user-form-password').required = true;
    document.getElementById('user-form-password-label').textContent = 'Password *';
    document.getElementById('user-form-avatar').value = '';
    document.getElementById('user-form-quick-templates').classList.remove('hidden');
    
    const err = document.getElementById('user-form-error');
    if (err) err.classList.add('hidden');

    document.getElementById('modal-user-form').classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  openEditUserModal(id) {
    const user = this.users.find(u => u.id === id);
    if (!user) return;

    document.getElementById('user-form-headline').textContent = `Edit Permissions: ${user.name}`;
    document.getElementById('user-form-submit-btn').textContent = 'Update Staff Profile';
    document.getElementById('user-form-id').value = user.id;
    document.getElementById('user-form-name').value = user.name;
    document.getElementById('user-form-email').value = user.email;
    document.getElementById('user-form-title').value = user.title;
    document.getElementById('user-form-role').value = user.role;
    document.getElementById('user-form-password').value = '';
    document.getElementById('user-form-password').required = false;
    document.getElementById('user-form-password-label').textContent = 'New Password (leave blank to keep)';
    document.getElementById('user-form-avatar').value = user.avatar || '';
    document.getElementById('user-form-quick-templates').classList.add('hidden');

    const err = document.getElementById('user-form-error');
    if (err) err.classList.add('hidden');

    document.getElementById('modal-user-form').classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  closeUserFormModal() {
    const modal = document.getElementById('modal-user-form');
    if (modal) modal.classList.add('hidden');
  }

  fillDoctorTemplate(name, email, title, role, avatar) {
    document.getElementById('user-form-name').value = name;
    document.getElementById('user-form-email').value = email;
    document.getElementById('user-form-title').value = title;
    document.getElementById('user-form-role').value = role;
    document.getElementById('user-form-avatar').value = avatar;
    document.getElementById('user-form-password').value = 'DoctorPass2026!';
  }

  async handleUserFormSubmit(e) {
    e.preventDefault();
    const id = document.getElementById('user-form-id').value;
    const name = document.getElementById('user-form-name').value.trim();
    const email = document.getElementById('user-form-email').value.trim();
    const title = document.getElementById('user-form-title').value.trim();
    const role = document.getElementById('user-form-role').value;
    const password = document.getElementById('user-form-password').value;
    const avatar = document.getElementById('user-form-avatar').value.trim();
    const err = document.getElementById('user-form-error');

    if (err) err.classList.add('hidden');

    const payload = { name, email, title, role, avatar };
    if (password) payload.password = password;

    const method = id ? 'PUT' : 'POST';
    const url = id ? `${API_BASE}/users/${id}` : `${API_BASE}/users`;

    try {
      const res = await fetch(url, {
        method: method,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.token}`
        },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok) {
        if (err) {
          err.textContent = data.error || 'Failed to save staff member.';
          err.classList.remove('hidden');
        } else {
          this.showToast(data.error || 'Failed to save staff member.', 'error');
        }
        return;
      }

      this.closeUserFormModal();
      this.showToast(data.message || 'Staff member saved successfully.');
      await this.loadUsers();
      await this.loadStats();
    } catch (error) {
      console.error(error);
      if (err) {
        err.textContent = 'Server error processing staff request.';
        err.classList.remove('hidden');
      }
    }
  }

  async deleteUser(id, name) {
    if (!confirm(`Are you sure you want to revoke editorial permissions for ${name}?`)) {
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/users/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${this.token}`
        }
      });

      const data = await res.json();
      if (!res.ok) {
        this.showToast(data.error || 'Failed to revoke permissions.', 'error');
        return;
      }

      this.showToast(data.message || `Revoked access for ${name}.`);
      await this.loadUsers();
      await this.loadStats();
    } catch (e) {
      console.error(e);
      this.showToast('Error revoking staff access.', 'error');
    }
  }
}

// Instantiate App
window.app = new MedPulseApp();
