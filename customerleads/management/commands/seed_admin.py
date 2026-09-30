from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from customerleads.models import UserProfile
from customerleads.firestore_utils import create_doc, get_by_query

User = get_user_model()

DEFAULT_USERS = [
    {
        'username': 'admin',
        'email': 'admin@auresancrm.com',
        'password': 'Admin@123',
        'first_name': 'System',
        'last_name': 'Admin',
        'role': 'admin',
        'is_superuser': True,
        'is_staff': True,
        'phone': '+256700000000',
        'department': 'Executive / IT',
        'bio': 'System Administrator Account',
    },
    {
        'username': 'manager',
        'email': 'manager@auresancrm.com',
        'password': 'Manager@123',
        'first_name': 'Sales',
        'last_name': 'Manager',
        'role': 'manager',
        'is_superuser': False,
        'is_staff': True,
        'phone': '+256700000002',
        'department': 'Management',
        'bio': 'Default Manager Account',
    },
    {
        'username': 'sales_rep',
        'email': 'salesrep@auresancrm.com',
        'password': 'Sales@123',
        'first_name': 'Alex',
        'last_name': 'Sales',
        'role': 'sales_rep',
        'is_superuser': False,
        'is_staff': False,
        'phone': '+256700000003',
        'department': 'Sales Department',
        'bio': 'Default Sales Representative Account',
    },
    {
        'username': 'viewer',
        'email': 'viewer@auresancrm.com',
        'password': 'Viewer@123',
        'first_name': 'Guest',
        'last_name': 'Viewer',
        'role': 'viewer',
        'is_superuser': False,
        'is_staff': False,
        'phone': '+256700000004',
        'department': 'Auditing',
        'bio': 'Read-Only Viewer Account',
    },
    {
        'username': 'developer',
        'email': 'developer@auresancrm.com',
        'password': 'Dev@123',
        'first_name': 'Lead',
        'last_name': 'Developer',
        'role': 'admin',
        'is_superuser': True,
        'is_staff': True,
        'phone': '+256700000001',
        'department': 'Engineering',
        'bio': 'Lead Developer Account',
    },
]

class Command(BaseCommand):
    help = 'Seeds default users and credentials for all roles in Django and Firebase Firestore'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE('--- Seeding Default Accounts for All Roles ---'))
        for udata in DEFAULT_USERS:
            username = udata['username']
            email = udata['email']
            password = udata['password']
            role = udata['role']
            
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'first_name': udata['first_name'],
                    'last_name': udata['last_name'],
                    'is_staff': udata['is_staff'],
                    'is_superuser': udata['is_superuser'],
                    'is_active': True,
                }
            )
            
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f"[CREATED] User: '{username}' ({role}) | Password: {password}"))
            else:
                user.set_password(password)
                user.is_staff = udata['is_staff']
                user.is_superuser = udata['is_superuser']
                user.save()
                self.stdout.write(self.style.WARNING(f"[UPDATED] User: '{username}' ({role})"))

            # Create or update profile
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.phone = udata['phone']
            profile.department = udata['department']
            profile.bio = udata['bio']
            profile.save()

            # Sync to Firestore 'users' collection
            try:
                firestore_user_data = {
                    'username': username,
                    'email': email,
                    'first_name': udata['first_name'],
                    'last_name': udata['last_name'],
                    'role': role,
                    'is_staff': udata['is_staff'],
                    'is_superuser': udata['is_superuser'],
                    'is_active': True,
                    'phone': udata['phone'],
                    'department': udata['department'],
                    'bio': udata['bio'],
                    'django_id': user.id,
                }
                # Check if exists in Firestore
                existing = get_by_query('users', filters=[('username', '==', username)])
                if existing:
                    from customerleads.firestore_utils import update_doc
                    update_doc('users', existing[0]._doc_id, firestore_user_data)
                else:
                    create_doc('users', firestore_user_data, doc_id=f"user_{user.id}")
                self.stdout.write(self.style.SUCCESS(f"  -> Synced '{username}' to Firebase Firestore collection 'users'"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  -> Failed to sync '{username}' to Firestore: {e}"))

        self.stdout.write(self.style.SUCCESS('--- Seeding completed successfully! ---'))
