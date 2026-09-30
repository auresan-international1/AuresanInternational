import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auresancrm.settings')
django.setup()

from customerleads.models import Lead
from customerleads.forms import LeadForm

lead = Lead.objects.all().first()
print(f"Got lead: {lead}")
try:
    form = LeadForm(instance=lead)
    print("Form instantiated successfully")
    print(form.as_p())
except Exception as e:
    import traceback
    traceback.print_exc()
