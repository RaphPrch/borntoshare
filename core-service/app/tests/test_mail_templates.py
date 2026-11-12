from datetime import datetime

from app.services import mail_templates as mt


def test_values_are_escaped_and_the_layout_is_complete():
    html = mt.layout(preheader="p", eyebrow="Nouvelle demande", title="<script>x</script> « Finance »", intro="a & b",
                     blocks=[mt.details([("Dossier", mt.code("\\\\corp.local\\Angers\\Finance"))]), mt.quote("Motif", "<b>")],
                     buttons=[mt.button("Voir", "http://h/a?x=1&y=2")], footer="f", badge="REQ-14")
    assert "<script>" not in html and "&lt;script&gt;" in html and "a &amp; b" in html and "&lt;b&gt;" in html
    assert 'href="http://h/a?x=1&amp;y=2"' in html and "REQ-14" in html and "NOUVELLE DEMANDE" in html
    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")


def test_the_date_block_names_the_day_in_french():
    block = mt.date_block(datetime(2026, 12, 12), "Finance · Modifier", "\\\\corp.local\\Angers\\Finance", 0.77, "23 jours sur 30 utilisés")
    assert "DÉCEMBRE" in block and "samedi" in block and "width:77%" in block
    assert mt.long_date(datetime(2026, 12, 12)) == "12 décembre 2026"


def test_an_alert_uses_the_alert_color():
    assert mt.ALERT in mt.layout(preheader="", eyebrow="Alerte", title="t", intro="i", footer="f", alert=True)
