#!/usr/bin/env python3
"""Clean up the mirrored site for static hosting."""
import os
import re
import glob
import posixpath
import shutil

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")

NOSCRIPT_PAGESPEED_RE = re.compile(
    r"<noscript>\s*<meta\s+HTTP-EQUIV=\"refresh\"[^>]*PageSpeed=noscript.*?</noscript>",
    re.DOTALL | re.IGNORECASE,
)
WCCP_TRACKER_RE = re.compile(
    r'<script[^>]*id=["\']wccp-activity-tracker-js-before["\'][^>]*>.*?</script>',
    re.DOTALL,
)
WCCP_TRACKER_SRC_RE = re.compile(
    r'<script[^>]*src=["\'][^"\']*wccp[^"\']*tracker[^"\']*["\'][^>]*>\s*</script>',
    re.DOTALL | re.IGNORECASE,
)
EMPTY_HREF_RE = re.compile(r'href=(["\'])\1')

FORMSPREE_ID = "FORM_ID_A_REMPLACER"  # remplacer par l'ID fourni par formspree.io

CONTACT_FORM = """
<form id="contact-form" class="forminator-ui forminator-custom-form forminator-design--default" method="POST" action="https://formspree.io/f/%(fid)s">
  <div class="forminator-response-message forminator-success" id="contact-success" style="display:none" role="alert">Merci ! Votre message a bien &eacute;t&eacute; envoy&eacute;. Nous vous r&eacute;pondrons rapidement.</div>
  <div class="forminator-row"><div class="forminator-col forminator-col-12"><div class="forminator-field">
    <label for="cf-name" class="forminator-label">Nom <span class="forminator-required">*</span></label>
    <input type="text" name="name" id="cf-name" class="forminator-input" required autocomplete="name"/>
  </div></div></div>
  <div class="forminator-row"><div class="forminator-col forminator-col-12"><div class="forminator-field">
    <label for="cf-email" class="forminator-label">Email <span class="forminator-required">*</span></label>
    <input type="email" name="email" id="cf-email" class="forminator-input" required autocomplete="email"/>
  </div></div></div>
  <div class="forminator-row"><div class="forminator-col forminator-col-12"><div class="forminator-field">
    <label for="cf-phone" class="forminator-label">T&eacute;l&eacute;phone</label>
    <input type="text" name="phone" id="cf-phone" class="forminator-input" autocomplete="tel"/>
  </div></div></div>
  <div class="forminator-row"><div class="forminator-col forminator-col-12"><div class="forminator-field">
    <label for="cf-message" class="forminator-label">Message</label>
    <textarea name="message" id="cf-message" class="forminator-textarea" style="--forminator-textarea-min-height:140px;" maxlength="180"></textarea>
  </div></div></div>
  <div class="forminator-row"><div class="forminator-col forminator-col-12"><div class="forminator-field">
    <label class="forminator-label">RGPD <span class="forminator-required">*</span></label>
    <div class="forminator-checkbox__wrapper"><label class="forminator-checkbox forminator-consent">
      <input type="checkbox" name="consent" value="accepted" required/><span class="forminator-checkbox-box" aria-hidden="true"></span></label>
      <div class="forminator-checkbox__label forminator-consent__label"><p>En soumettant ce formulaire, j&rsquo;accepte que mes donn&eacute;es soient utilis&eacute;es pour me recontacter</p></div>
    </div>
  </div></div></div>
  <input type="text" name="_gotcha" style="display:none" tabindex="-1" autocomplete="off"/>
  <input type="hidden" name="_subject" value="Nouveau message — maison-lavande-provence.fr"/>
  <input type="hidden" name="_next" value="https://www.maison-lavande-provence.fr/contact/?sent=1"/>
  <div class="forminator-row forminator-row-last"><div class="forminator-col"><div class="forminator-field">
    <button type="submit" class="forminator-button forminator-button-submit">Envoyer</button>
  </div></div></div>
</form>
<!-- TODO: remplacez %(fid)s par votre ID Formspree (https://formspree.io — gratuit) -->
<script>if(location.search.indexOf("sent=1")!==-1){var s=document.getElementById("contact-success");if(s)s.style.display="block";}</script>
""" % {"fid": FORMSPREE_ID}


def home_prefix(local):
    """Relative prefix to site root from a page local path like 'a-propos/index.html'."""
    d = posixpath.dirname(local)
    if not d:
        return "./"
    depth = len([p for p in d.split("/") if p])
    return "/".join([".."] * depth) + "/"


def clean_html(path, text):
    local = os.path.relpath(path, ROOT)
    orig = text

    # 1) remove PageSpeed noscript refresh/hide blocks
    text = NOSCRIPT_PAGESPEED_RE.sub("", text)

    # 2) remove wccp ajax tracker (calls dead admin-ajax.php)
    text = WCCP_TRACKER_RE.sub("", text)
    text = WCCP_TRACKER_SRC_RE.sub("", text)

    # 3) fix href="" -> link to site root
    text = EMPTY_HREF_RE.sub(lambda m: f'href={m.group(1)}{home_prefix(local)}{m.group(1)}', text)

    return text, text != orig


def fix_contact(path, text):
    """Replace Forminator form + its init scripts with a static Formspree form."""
    # remove forminator placeholder div + hidden form
    text, n1 = re.subn(
        r'<div class="forminator-ui[^"]*"[^>]*data-form="forminator-module-1842"[^>]*><br/></div>'
        r'<form id="forminator-module-1842".*?</form>',
        CONTACT_FORM.strip(),
        text,
        flags=re.DOTALL,
    )
    # remove forminator init/nonce scripts
    text, n2 = re.subn(
        r'<script type="text/javascript">jQuery\(function\(\)\{jQuery\.ajax\(\{url:[^<]*forminator_get_nonce[^<]*</script>',
        "",
        text,
        flags=re.DOTALL,
    )
    text, n3 = re.subn(
        r'<script type="text/javascript">jQuery\(function\(\)\{window\.Forminator_Cform.*?</script>',
        "",
        text,
        flags=re.DOTALL,
    )
    print(f"contact: form remplacé={bool(n1)} scripts_supprimés={n2 + n3}")
    return text


def main():
    # remove orphaned blog category dir
    cat = os.path.join(ROOT, "category")
    if os.path.isdir(cat):
        shutil.rmtree(cat)
        print("supprimé: category/")

    for path in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        text, _ = clean_html(path, text)
        local = os.path.relpath(path, ROOT)
        if local == os.path.join("contact", "index.html"):
            text = fix_contact(path, text)
        if local == os.path.join("conditions-generales-de-vente-cgv", "index.html"):
            # remove comment form + category links (page was a WP "post")
            text = re.sub(
                r'<div id="respond".*?</div><!-- #respond -->',
                "",
                text,
                flags=re.DOTALL,
            )
            text = re.sub(
                r'<div class="taxonomy-category[^>]*>.*?</div>',
                "",
                text,
                flags=re.DOTALL,
            )
            text = text.replace(
                '<a href="../category/uncategorized/">Uncategorized</a>', "Uncategorized"
            )
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    # extra repo files for GitHub Pages
    extras = {
        "CNAME": "www.maison-lavande-provence.fr\n",
        ".nojekyll": "",
        "robots.txt": (
            "User-agent: *\nAllow: /\n\n"
            "Sitemap: https://www.maison-lavande-provence.fr/sitemap.xml\n"
        ),
    }
    pages = sorted(
        d for d in os.listdir(ROOT)
        if os.path.isfile(os.path.join(ROOT, d, "index.html"))
    )
    urls = ["https://www.maison-lavande-provence.fr/"] + [
        f"https://www.maison-lavande-provence.fr/{p}/" for p in pages
    ]
    extras["sitemap.xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
        + "\n</urlset>\n"
    )
    for name, content in extras.items():
        with open(os.path.join(ROOT, name), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"écrit: {name}")

    # 404 page (simple, dans le style du site)
    with open(os.path.join(ROOT, "404.html"), "w", encoding="utf-8") as f:
        f.write(
            "<!DOCTYPE html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
            "<title>Page introuvable — Maison Lavande Provence</title>"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<style>body{font-family:Georgia,serif;display:flex;min-height:100vh;margin:0;"
            "align-items:center;justify-content:center;background:#faf7f2;color:#3b3b3b}"
            "main{text-align:center;padding:2rem}h1{font-size:2.2rem;font-weight:normal}"
            "a{color:#7a5c9e;text-decoration:none;border-bottom:1px solid}</style></head>"
            "<body><main><h1>Page introuvable</h1>"
            "<p>La page que vous cherchez n&rsquo;existe pas ou a &eacute;t&eacute; d&eacute;plac&eacute;e.</p>"
            "<p><a href=\"/\">Retour &agrave; l&rsquo;accueil</a></p></main></body></html>\n"
        )
    print("écrit: 404.html")


if __name__ == "__main__":
    main()
