from django import template

register = template.Library()


@register.simple_tag
def render_widget(field):
    """Render widget dengan aria-describedby ke bantuan & error, dan aria-invalid bila error."""
    described_by = []
    if field.help_text:
        described_by.append(f"{field.auto_id}_helptext")
    if field.errors:
        described_by.append(f"{field.auto_id}_error")
    attrs = {}
    if described_by:
        attrs["aria-describedby"] = " ".join(described_by)
    if field.errors:
        attrs["aria-invalid"] = "true"
    return field.as_widget(attrs=attrs)
