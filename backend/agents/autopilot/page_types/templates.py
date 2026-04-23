"""
HTML reference templates for the design stage.

These are structural skeletons that the design agent uses as a starting point.
The agent fills in the content from the copywrite stage and customizes
the CSS based on client brand data from memory.

Each template uses CSS custom properties so clients can rebrand by changing
a few variables. WordPress-compatible class names throughout.
"""

SERVICE_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{TITLE_TAG}}</title>
    <meta name="description" content="{{META_DESCRIPTION}}">
    <meta property="og:title" content="{{TITLE_TAG}}">
    <meta property="og:description" content="{{META_DESCRIPTION}}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="{{CANONICAL_URL}}">
    <meta property="og:image" content="{{OG_IMAGE}}">
    <link rel="canonical" href="{{CANONICAL_URL}}">
    {{SCHEMA_JSON_LD}}
    <style>
        :root {
            --primary: #0051FF;
            --secondary: #00184D;
            --accent: #C8FF00;
            --text: #1a1a2e;
            --text-light: #6b7280;
            --bg: #ffffff;
            --bg-alt: #f8fafc;
            --border: #e5e7eb;
            --radius: 8px;
            --max-w: 1200px;
        }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: var(--text); line-height: 1.6; }
        img { max-width: 100%; height: auto; display: block; }
        .container { max-width: var(--max-w); margin: 0 auto; padding: 0 1.5rem; }

        /* Hero */
        .hero { background: var(--secondary); color: #fff; padding: 4rem 0; }
        .hero h1 { font-size: 2.5rem; font-weight: 800; margin-bottom: 1rem; line-height: 1.15; }
        .hero p { font-size: 1.15rem; opacity: 0.9; max-width: 640px; margin-bottom: 2rem; }
        .hero .cta-btn { display: inline-block; background: var(--accent); color: var(--secondary); font-weight: 700; padding: 0.85rem 2rem; border-radius: var(--radius); text-decoration: none; font-size: 1.05rem; }
        .hero .trust-badges { display: flex; gap: 1.5rem; margin-top: 2rem; flex-wrap: wrap; }
        .hero .trust-badges span { font-size: 0.9rem; opacity: 0.8; }

        /* Trust Signals */
        .trust-section { background: var(--bg-alt); padding: 3rem 0; }
        .trust-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; }
        .trust-card { text-align: center; padding: 1.5rem; }
        .trust-card .number { font-size: 2rem; font-weight: 800; color: var(--primary); }
        .trust-card p { color: var(--text-light); margin-top: 0.25rem; }

        /* Content Sections */
        .content-section { padding: 3.5rem 0; }
        .content-section:nth-child(even) { background: var(--bg-alt); }
        .content-section h2 { font-size: 1.75rem; font-weight: 700; margin-bottom: 1rem; color: var(--secondary); }
        .content-section h3 { font-size: 1.25rem; font-weight: 600; margin: 1.5rem 0 0.75rem; }
        .content-section p { margin-bottom: 1rem; max-width: 720px; }
        .content-section ul, .content-section ol { margin: 1rem 0; padding-left: 1.5rem; }
        .content-section li { margin-bottom: 0.5rem; }

        /* Pricing */
        .pricing-section { padding: 3.5rem 0; background: var(--bg-alt); }
        .price-table { width: 100%; border-collapse: collapse; margin: 1.5rem 0; }
        .price-table th, .price-table td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }
        .price-table th { background: var(--secondary); color: #fff; font-weight: 600; }

        /* Process */
        .process-steps { counter-reset: step; list-style: none; padding: 0; }
        .process-steps li { counter-increment: step; padding: 1rem 0 1rem 3.5rem; position: relative; border-left: 2px solid var(--border); margin-left: 1rem; }
        .process-steps li::before { content: counter(step); position: absolute; left: -1rem; width: 2rem; height: 2rem; background: var(--primary); color: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.85rem; }

        /* FAQ */
        .faq-section { padding: 3.5rem 0; }
        .faq-item { border-bottom: 1px solid var(--border); padding: 1.25rem 0; }
        .faq-item h3 { font-size: 1.1rem; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
        .faq-item h3::after { content: '+'; font-size: 1.5rem; color: var(--primary); }
        .faq-item.open h3::after { content: '−'; }
        .faq-item .faq-answer { max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }
        .faq-item.open .faq-answer { max-height: 500px; }
        .faq-answer p { padding-top: 0.75rem; color: var(--text-light); }

        /* CTA Section */
        .cta-section { background: var(--secondary); color: #fff; padding: 3.5rem 0; text-align: center; }
        .cta-section h2 { font-size: 2rem; margin-bottom: 1rem; }
        .cta-section p { opacity: 0.9; margin-bottom: 2rem; max-width: 600px; margin-left: auto; margin-right: auto; }
        .cta-section .cta-btn { display: inline-block; background: var(--accent); color: var(--secondary); font-weight: 700; padding: 1rem 2.5rem; border-radius: var(--radius); text-decoration: none; font-size: 1.1rem; }
        .cta-section .phone { font-size: 1.5rem; font-weight: 800; margin-top: 1rem; }
        .cta-section .phone a { color: var(--accent); text-decoration: none; }

        /* Responsive */
        @media (max-width: 768px) {
            .hero h1 { font-size: 1.75rem; }
            .hero { padding: 2.5rem 0; }
            .content-section, .pricing-section, .faq-section { padding: 2.5rem 0; }
        }
    </style>
</head>
<body>
    <section class="hero">
        <div class="container">
            <h1>{{H1}}</h1>
            <p>{{HERO_PARAGRAPH}}</p>
            <a href="tel:{{PHONE}}" class="cta-btn">{{CTA_TEXT}}</a>
            <div class="trust-badges">
                <span>{{TRUST_BADGE_1}}</span>
                <span>{{TRUST_BADGE_2}}</span>
                <span>{{TRUST_BADGE_3}}</span>
            </div>
        </div>
    </section>

    <section class="trust-section">
        <div class="container">
            <div class="trust-grid">
                <!-- Trust signal cards: years, reviews, projects, certifications -->
            </div>
        </div>
    </section>

    <section class="content-section">
        <div class="container">
            <h2>{{WHATS_INCLUDED_HEADING}}</h2>
            <!-- Scope of work content -->
        </div>
    </section>

    <section class="pricing-section">
        <div class="container">
            <h2>{{PRICING_HEADING}}</h2>
            <!-- Price ranges, factors, transparency content -->
        </div>
    </section>

    <section class="content-section">
        <div class="container">
            <h2>{{PROCESS_HEADING}}</h2>
            <ol class="process-steps">
                <!-- Step-by-step process -->
            </ol>
        </div>
    </section>

    <section class="content-section">
        <div class="container">
            <h2>{{LOCAL_HEADING}}</h2>
            <!-- Local proof, neighborhoods, landmarks -->
        </div>
    </section>

    <section class="faq-section">
        <div class="container">
            <h2>Frequently Asked Questions</h2>
            <!-- FAQ items with accordion -->
        </div>
    </section>

    <section class="cta-section">
        <div class="container">
            <h2>{{FINAL_CTA_HEADING}}</h2>
            <p>{{FINAL_CTA_PARAGRAPH}}</p>
            <a href="tel:{{PHONE}}" class="cta-btn">{{FINAL_CTA_BUTTON}}</a>
            <div class="phone"><a href="tel:{{PHONE}}">{{PHONE}}</a></div>
        </div>
    </section>

    <script>
        document.querySelectorAll('.faq-item h3').forEach(q => {
            q.addEventListener('click', () => q.parentElement.classList.toggle('open'));
        });
    </script>
</body>
</html>"""


LOCATION_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{TITLE_TAG}}</title>
    <meta name="description" content="{{META_DESCRIPTION}}">
    <meta property="og:title" content="{{TITLE_TAG}}">
    <meta property="og:description" content="{{META_DESCRIPTION}}">
    <meta property="og:type" content="website">
    <link rel="canonical" href="{{CANONICAL_URL}}">
    {{SCHEMA_JSON_LD}}
    <style>
        :root {
            --primary: #0051FF;
            --secondary: #00184D;
            --accent: #C8FF00;
            --text: #1a1a2e;
            --text-light: #6b7280;
            --bg: #ffffff;
            --bg-alt: #f8fafc;
            --border: #e5e7eb;
            --radius: 8px;
            --max-w: 1200px;
        }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: var(--text); line-height: 1.6; }
        img { max-width: 100%; height: auto; display: block; }
        .container { max-width: var(--max-w); margin: 0 auto; padding: 0 1.5rem; }

        .hero { background: var(--secondary); color: #fff; padding: 4rem 0; }
        .hero h1 { font-size: 2.5rem; font-weight: 800; margin-bottom: 1rem; }
        .hero p { font-size: 1.15rem; opacity: 0.9; max-width: 640px; margin-bottom: 2rem; }
        .hero .cta-btn { display: inline-block; background: var(--accent); color: var(--secondary); font-weight: 700; padding: 0.85rem 2rem; border-radius: var(--radius); text-decoration: none; }

        .section { padding: 3.5rem 0; }
        .section:nth-child(even) { background: var(--bg-alt); }
        .section h2 { font-size: 1.75rem; font-weight: 700; margin-bottom: 1rem; color: var(--secondary); }
        .section p { margin-bottom: 1rem; max-width: 720px; }

        .services-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; margin-top: 1.5rem; }
        .service-card { background: #fff; border: 1px solid var(--border); border-radius: var(--radius); padding: 1.5rem; }
        .service-card h3 { font-size: 1.15rem; color: var(--primary); margin-bottom: 0.5rem; }
        .service-card a { color: var(--primary); font-weight: 600; text-decoration: none; }

        .areas-list { display: flex; flex-wrap: wrap; gap: 0.75rem; list-style: none; padding: 0; margin-top: 1rem; }
        .areas-list li { background: var(--bg-alt); border: 1px solid var(--border); padding: 0.5rem 1rem; border-radius: 999px; font-size: 0.9rem; }
        .areas-list li a { color: var(--primary); text-decoration: none; }

        .faq-item { border-bottom: 1px solid var(--border); padding: 1.25rem 0; }
        .faq-item h3 { font-size: 1.1rem; cursor: pointer; display: flex; justify-content: space-between; }
        .faq-item h3::after { content: '+'; font-size: 1.5rem; color: var(--primary); }
        .faq-item.open h3::after { content: '−'; }
        .faq-item .faq-answer { max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }
        .faq-item.open .faq-answer { max-height: 500px; }

        .cta-section { background: var(--secondary); color: #fff; padding: 3.5rem 0; text-align: center; }
        .cta-section h2 { font-size: 2rem; margin-bottom: 1rem; }
        .cta-section .cta-btn { display: inline-block; background: var(--accent); color: var(--secondary); font-weight: 700; padding: 1rem 2.5rem; border-radius: var(--radius); text-decoration: none; font-size: 1.1rem; }
        .cta-section .phone { font-size: 1.5rem; font-weight: 800; margin-top: 1rem; }
        .cta-section .phone a { color: var(--accent); text-decoration: none; }

        @media (max-width: 768px) { .hero h1 { font-size: 1.75rem; } .hero { padding: 2.5rem 0; } }
    </style>
</head>
<body>
    <section class="hero">
        <div class="container">
            <h1>{{H1}}</h1>
            <p>{{HERO_PARAGRAPH}}</p>
            <a href="tel:{{PHONE}}" class="cta-btn">{{CTA_TEXT}}</a>
        </div>
    </section>

    <section class="section">
        <div class="container">
            <h2>{{LOCAL_CONTEXT_HEADING}}</h2>
            <!-- Local context: neighborhoods, drive time, area-specific details -->
        </div>
    </section>

    <section class="section">
        <div class="container">
            <h2>Our Services in {{LOCATION}}</h2>
            <div class="services-grid">
                <!-- Service cards linking to full service pages -->
            </div>
        </div>
    </section>

    <section class="section">
        <div class="container">
            <h2>Areas We Serve Near {{LOCATION}}</h2>
            <ul class="areas-list">
                <!-- Nearby area pills linking to other location pages -->
            </ul>
        </div>
    </section>

    <section class="section">
        <div class="container">
            <h2>Frequently Asked Questions</h2>
            <!-- FAQ items -->
        </div>
    </section>

    <section class="cta-section">
        <div class="container">
            <h2>{{FINAL_CTA_HEADING}}</h2>
            <a href="tel:{{PHONE}}" class="cta-btn">{{FINAL_CTA_BUTTON}}</a>
            <div class="phone"><a href="tel:{{PHONE}}">{{PHONE}}</a></div>
        </div>
    </section>

    <script>
        document.querySelectorAll('.faq-item h3').forEach(q => {
            q.addEventListener('click', () => q.parentElement.classList.toggle('open'));
        });
    </script>
</body>
</html>"""


BLOG_POST_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{TITLE_TAG}}</title>
    <meta name="description" content="{{META_DESCRIPTION}}">
    <meta property="og:title" content="{{TITLE_TAG}}">
    <meta property="og:description" content="{{META_DESCRIPTION}}">
    <meta property="og:type" content="article">
    <meta property="article:published_time" content="{{PUBLISH_DATE}}">
    <link rel="canonical" href="{{CANONICAL_URL}}">
    {{SCHEMA_JSON_LD}}
    <style>
        :root {
            --primary: #0051FF;
            --secondary: #00184D;
            --accent: #C8FF00;
            --text: #1a1a2e;
            --text-light: #6b7280;
            --bg: #ffffff;
            --bg-alt: #f8fafc;
            --border: #e5e7eb;
            --radius: 8px;
            --max-w: 800px;
        }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: var(--text); line-height: 1.7; }
        img { max-width: 100%; height: auto; display: block; border-radius: var(--radius); }

        .article-header { background: var(--secondary); color: #fff; padding: 4rem 0 3rem; }
        .article-header .container { max-width: var(--max-w); margin: 0 auto; padding: 0 1.5rem; }
        .article-header h1 { font-size: 2.25rem; font-weight: 800; line-height: 1.2; margin-bottom: 1rem; }
        .article-meta { display: flex; gap: 1.5rem; font-size: 0.9rem; opacity: 0.8; }

        .article-body { max-width: var(--max-w); margin: 0 auto; padding: 3rem 1.5rem; }
        .article-body h2 { font-size: 1.5rem; font-weight: 700; margin: 2.5rem 0 1rem; color: var(--secondary); padding-bottom: 0.5rem; border-bottom: 2px solid var(--border); }
        .article-body h3 { font-size: 1.2rem; font-weight: 600; margin: 1.75rem 0 0.75rem; }
        .article-body p { margin-bottom: 1.25rem; }
        .article-body ul, .article-body ol { margin: 1rem 0; padding-left: 1.5rem; }
        .article-body li { margin-bottom: 0.5rem; }
        .article-body blockquote { border-left: 3px solid var(--primary); padding: 1rem 1.5rem; margin: 1.5rem 0; background: var(--bg-alt); border-radius: 0 var(--radius) var(--radius) 0; }
        .article-body strong { color: var(--secondary); }

        /* Table of Contents */
        .toc { background: var(--bg-alt); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.5rem; margin-bottom: 2rem; }
        .toc h2 { font-size: 1.1rem; margin: 0 0 0.75rem; border: none; padding: 0; }
        .toc ul { list-style: none; padding: 0; }
        .toc li { margin-bottom: 0.4rem; }
        .toc a { color: var(--primary); text-decoration: none; }

        /* Author Bio */
        .author-bio { display: flex; gap: 1.25rem; align-items: flex-start; padding: 1.5rem; background: var(--bg-alt); border-radius: var(--radius); margin-top: 3rem; }
        .author-bio img { width: 64px; height: 64px; border-radius: 50%; flex-shrink: 0; }
        .author-bio .author-name { font-weight: 700; color: var(--secondary); }
        .author-bio p { font-size: 0.9rem; color: var(--text-light); margin-top: 0.25rem; }

        /* CTA */
        .article-cta { background: var(--bg-alt); border: 2px solid var(--primary); border-radius: var(--radius); padding: 2rem; text-align: center; margin-top: 2.5rem; }
        .article-cta h3 { font-size: 1.25rem; color: var(--secondary); margin-bottom: 0.75rem; }
        .article-cta .cta-btn { display: inline-block; background: var(--primary); color: #fff; font-weight: 700; padding: 0.75rem 2rem; border-radius: var(--radius); text-decoration: none; margin-top: 1rem; }

        /* FAQ */
        .faq-item { border-bottom: 1px solid var(--border); padding: 1rem 0; }
        .faq-item h3 { font-size: 1.05rem; cursor: pointer; margin: 0; display: flex; justify-content: space-between; }
        .faq-item h3::after { content: '+'; font-size: 1.5rem; color: var(--primary); }
        .faq-item.open h3::after { content: '−'; }
        .faq-item .faq-answer { max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }
        .faq-item.open .faq-answer { max-height: 500px; }

        @media (max-width: 768px) { .article-header h1 { font-size: 1.6rem; } }
    </style>
</head>
<body>
    <header class="article-header">
        <div class="container">
            <h1>{{H1}}</h1>
            <div class="article-meta">
                <span>By {{AUTHOR_NAME}}</span>
                <span>{{PUBLISH_DATE}}</span>
                <span>{{READ_TIME}} min read</span>
            </div>
        </div>
    </header>

    <article class="article-body">
        <nav class="toc">
            <h2>In This Article</h2>
            <ul>
                <!-- Auto-generated from H2 headings -->
            </ul>
        </nav>

        <!-- Article content sections -->

        <div class="article-cta">
            <h3>{{CTA_HEADING}}</h3>
            <p>{{CTA_PARAGRAPH}}</p>
            <a href="tel:{{PHONE}}" class="cta-btn">{{CTA_BUTTON}}</a>
        </div>

        <div class="author-bio">
            <img src="{{AUTHOR_IMAGE}}" alt="{{AUTHOR_NAME}}" loading="lazy">
            <div>
                <div class="author-name">{{AUTHOR_NAME}}</div>
                <p>{{AUTHOR_BIO}}</p>
            </div>
        </div>
    </article>

    <script>
        document.querySelectorAll('.faq-item h3').forEach(q => {
            q.addEventListener('click', () => q.parentElement.classList.toggle('open'));
        });
    </script>
</body>
</html>"""


# Map page types to their templates
PAGE_TEMPLATES = {
    "service-page": SERVICE_PAGE_HTML,
    "location-page": LOCATION_PAGE_HTML,
    "blog-post": BLOG_POST_HTML,
}
