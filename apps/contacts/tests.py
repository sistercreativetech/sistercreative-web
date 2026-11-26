from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User

from . import services
from .messages import render_message, unknown_variables
from .models import Contact, ContactGroup, MessageTemplate

PASSWORD = "Rahasia-Kuat-2026!"


def make_member(email, **extra):
    extra.setdefault("full_name", "Member Uji")
    extra.setdefault("status", User.Status.ACTIVE)
    return User.objects.create_user(email=email, password=PASSWORD, **extra)


def csv_file(text, name="kontak.csv", encoding="utf-8"):
    return SimpleUploadedFile(name, text.encode(encoding), content_type="text/csv")


class MessageRenderTests(SimpleTestCase):
    def test_render_variables(self):
        body = "Halo {nama_depan} ({nama}), nomor Anda {nomor}."
        self.assertEqual(
            render_message(body, name="Siti  Aminah", phone="6281234567890"),
            "Halo Siti (Siti Aminah), nomor Anda +6281234567890.",
        )

    def test_fallback_when_no_name(self):
        self.assertEqual(render_message("Halo {nama_depan}", name=""), "Halo Bapak/Ibu")

    def test_unknown_and_dangerous_placeholders_are_left_untouched(self):
        body = "Tes {harga} {nama.__class__} {0}"
        self.assertEqual(render_message(body, name="Budi"), body)
        self.assertEqual(unknown_variables("{nama} {harga} {harga} {alamat}"), ["harga", "alamat"])


class CsvParsingTests(SimpleTestCase):
    def test_header_with_comma(self):
        rows = services.parse_csv(b"nama,nomor\nSiti,0812-3456-7890\n")
        self.assertEqual(rows, [(2, "Siti", "0812-3456-7890")])

    def test_excel_semicolon_with_bom_and_alias_headers(self):
        raw = "﻿Nama Lengkap;No. WA\nBudi Santoso;+62 813 2222 3333\n".encode()
        self.assertEqual(services.parse_csv(raw), [(2, "Budi Santoso", "+62 813 2222 3333")])

    def test_reversed_column_order(self):
        rows = services.parse_csv(b"whatsapp,name\n081234567890,Rina\n")
        self.assertEqual(rows, [(2, "Rina", "081234567890")])

    def test_no_header_two_columns(self):
        rows = services.parse_csv(b"Siti,081234567890\nBudi,081311112222\n")
        self.assertEqual([r[1] for r in rows], ["Siti", "Budi"])

    def test_single_column_of_numbers(self):
        rows = services.parse_csv(b"081234567890\n081311112222\n")
        self.assertEqual([r[2] for r in rows], ["081234567890", "081311112222"])

    def test_latin1_fallback(self):
        rows = services.parse_csv("nama,nomor\nJosé,081234567890\n".encode("cp1252"))
        self.assertEqual(rows[0][1], "José")

    def test_empty_file(self):
        with self.assertRaises(services.ImportFileError):
            services.parse_csv(b"\n\n")

    @override_settings(CONTACT_IMPORT_MAX_ROWS=2)
    def test_row_limit(self):
        with self.assertRaisesMessage(services.ImportFileError, "Maksimal 2 baris"):
            services.parse_csv(b"nama,nomor\na,0811111111\nb,0812222222\nc,0813333333\n")


class ImportServiceTests(TestCase):
    def setUp(self):
        self.member = make_member("siti@contoh.id")
        self.other = make_member("budi@contoh.id")

    def test_import_counts_and_normalizes(self):
        Contact.objects.create(owner=self.member, name="Lama", phone="6281111111111")
        raw = (
            b"nama,nomor\n"
            b"Siti,0812-3456-7890\n"
            b"Siti lagi,+62 812 3456 7890\n"  # ganda di file
            b"Lama,081111111111\n"  # sudah ada
            b"Salah,12345\n"
            b"Excel,6.28123E+12\n"
        )
        result = services.import_contacts(self.member, raw)
        self.assertEqual(result.created, 1)
        self.assertEqual(result.existing, 1)
        self.assertEqual(result.duplicates_in_file, 1)
        self.assertEqual(result.invalid_count, 2)
        self.assertEqual(result.invalid_rows[0][0], 5)
        self.assertIn("E+", result.invalid_rows[1][2])
        self.assertTrue(
            Contact.objects.filter(owner=self.member, phone="6281234567890", name="Siti").exists()
        )

    def test_same_number_allowed_for_different_members(self):
        Contact.objects.create(owner=self.other, phone="6281234567890")
        result = services.import_contacts(self.member, b"nomor\n081234567890\n")
        self.assertEqual(result.created, 1)

    def test_assigns_new_and_existing_contacts_to_group(self):
        existing = Contact.objects.create(owner=self.member, phone="6281111111111")
        group = ContactGroup.objects.create(owner=self.member, name="Wali murid")
        services.import_contacts(self.member, b"nomor\n081111111111\n081222222222\n", group)
        self.assertEqual(group.contacts.count(), 2)
        self.assertIn(existing, group.contacts.all())

    def test_rejects_other_members_group(self):
        foreign = ContactGroup.objects.create(owner=self.other, name="Grup orang lain")
        with self.assertRaises(PermissionError):
            services.import_contacts(self.member, b"nomor\n081222222222\n", foreign)
        self.assertFalse(Contact.objects.filter(owner=self.member).exists())

    @override_settings(MAX_CONTACTS_PER_MEMBER=2)
    def test_respects_contact_limit(self):
        Contact.objects.create(owner=self.member, phone="6281111111111")
        result = services.import_contacts(self.member, b"nomor\n081222222222\n081333333333\n")
        self.assertEqual(result.created, 1)
        self.assertEqual(result.skipped_over_limit, 1)


class MemberAreaTestCase(TestCase):
    def setUp(self):
        self.member = make_member("siti@contoh.id", full_name="Siti Aminah")
        self.other = make_member("budi@contoh.id", full_name="Budi Santoso")
        self.client.force_login(self.member)


class AccessTests(MemberAreaTestCase):
    def test_pending_member_cannot_use_contacts(self):
        pending = make_member("baru@contoh.id", status=User.Status.PENDING)
        self.client.force_login(pending)
        for name in ["members:contact_list", "members:group_list", "members:template_list"]:
            self.assertRedirects(self.client.get(reverse(name)), reverse("members:pending"))

    def test_cannot_touch_other_members_data(self):
        contact = Contact.objects.create(owner=self.other, name="Rahasia", phone="6289999999999")
        group = ContactGroup.objects.create(owner=self.other, name="Grup Budi")
        template = MessageTemplate.objects.create(owner=self.other, name="Promo", body="Halo")
        for name, obj in [
            ("members:contact_update", contact),
            ("members:contact_delete", contact),
            ("members:group_update", group),
            ("members:group_delete", group),
            ("members:template_update", template),
            ("members:template_delete", template),
        ]:
            url = reverse(name, args=[obj.pk])
            self.assertEqual(self.client.get(url).status_code, 404, name)
            self.assertEqual(self.client.post(url, {"name": "Ubah"}).status_code, 404, name)
        self.assertTrue(Contact.objects.filter(pk=contact.pk, name="Rahasia").exists())
        self.assertNotContains(self.client.get(reverse("members:contact_list")), "Rahasia")
        self.assertNotContains(self.client.get(reverse("members:group_list")), "Grup Budi")

    def test_cannot_assign_contact_to_other_members_group(self):
        foreign = ContactGroup.objects.create(owner=self.other, name="Grup Budi")
        response = self.client.post(
            reverse("members:contact_create"),
            {"name": "Rina", "phone": "081234567890", "groups": [foreign.pk]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Contact.objects.filter(owner=self.member).exists())


class ContactViewTests(MemberAreaTestCase):
    def test_create_contact_normalizes_phone(self):
        group = ContactGroup.objects.create(owner=self.member, name="Pelanggan")
        response = self.client.post(
            reverse("members:contact_create"),
            {"name": "  Rina   Wati ", "phone": "0812-3456-7890", "groups": [group.pk]},
        )
        self.assertRedirects(response, reverse("members:contact_list"))
        contact = Contact.objects.get(owner=self.member)
        self.assertEqual((contact.name, contact.phone), ("Rina Wati", "6281234567890"))
        self.assertEqual(list(contact.groups.all()), [group])

    def test_duplicate_phone_rejected(self):
        Contact.objects.create(owner=self.member, phone="6281234567890")
        response = self.client.post(
            reverse("members:contact_create"), {"name": "X", "phone": "+62 812-3456-7890"}
        )
        self.assertContains(response, "sudah ada di daftar kontak")

    def test_opt_out_sets_timestamp(self):
        contact = Contact.objects.create(owner=self.member, name="Rina", phone="6281234567890")
        self.client.post(
            reverse("members:contact_update", args=[contact.pk]),
            {"name": "Rina", "phone": "081234567890", "is_opted_out": "on"},
        )
        contact.refresh_from_db()
        self.assertTrue(contact.is_opted_out)
        self.assertIsNotNone(contact.opted_out_at)

    def test_list_search_and_filters(self):
        group = ContactGroup.objects.create(owner=self.member, name="VIP")
        vip = Contact.objects.create(owner=self.member, name="Andi", phone="6281111111111")
        vip.groups.add(group)
        Contact.objects.create(
            owner=self.member, name="Berhenti", phone="6282222222222", is_opted_out=True
        )
        url = reverse("members:contact_list")
        self.assertContains(self.client.get(url, {"q": "0811-1111"}), "Andi")
        self.assertNotContains(self.client.get(url, {"group": group.pk}), "+6282222222222")
        opted = self.client.get(url, {"subscription": "opted_out"})
        self.assertContains(opted, "+6282222222222")
        self.assertNotContains(opted, "+6281111111111")

    def test_delete_contact(self):
        contact = Contact.objects.create(owner=self.member, phone="6281234567890")
        url = reverse("members:contact_delete", args=[contact.pk])
        self.assertRedirects(self.client.post(url), reverse("members:contact_list"))
        self.assertFalse(Contact.objects.filter(pk=contact.pk).exists())


class ImportViewTests(MemberAreaTestCase):
    url = reverse("members:contact_import")

    def test_import_into_new_group_shows_summary(self):
        response = self.client.post(
            self.url,
            {
                "file": csv_file("nama;nomor\nSiti;081234567890\nSalah;123\n"),
                "new_group_name": "Wali murid kelas 5",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hasil impor")
        self.assertContains(response, "Wali murid kelas 5")
        group = ContactGroup.objects.get(owner=self.member, name="Wali murid kelas 5")
        self.assertEqual(group.contacts.count(), 1)

    def test_rejects_non_csv_extension(self):
        response = self.client.post(
            self.url, {"file": csv_file("nama,nomor\n", name="kontak.xlsx")}
        )
        self.assertContains(response, 'aria-invalid="true"')
        self.assertFalse(Contact.objects.exists())

    @override_settings(CONTACT_IMPORT_MAX_BYTES=10)
    def test_rejects_large_file(self):
        response = self.client.post(self.url, {"file": csv_file("nama,nomor\n" * 5)})
        self.assertContains(response, "Ukuran file maksimal")

    def test_unreadable_file_shows_error(self):
        response = self.client.post(self.url, {"file": csv_file("\n\n")})
        self.assertContains(response, "File CSV kosong")

    def test_cannot_pick_both_group_options(self):
        group = ContactGroup.objects.create(owner=self.member, name="Lama")
        response = self.client.post(
            self.url,
            {"file": csv_file("nomor\n081234567890\n"), "group": group.pk, "new_group_name": "B"},
        )
        self.assertContains(response, "jangan keduanya")

    def test_sample_csv_download(self):
        response = self.client.get(reverse("members:contact_sample"))
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(len(services.parse_csv(response.content)), 2)


class GroupViewTests(MemberAreaTestCase):
    def test_create_group_and_duplicate_name_case_insensitive(self):
        self.client.post(reverse("members:group_create"), {"name": "Pelanggan Lama"})
        response = self.client.post(reverse("members:group_create"), {"name": "pelanggan lama"})
        self.assertContains(response, "sudah punya grup")
        self.assertEqual(ContactGroup.objects.filter(owner=self.member).count(), 1)

    def test_other_member_can_use_same_group_name(self):
        ContactGroup.objects.create(owner=self.other, name="Pelanggan")
        self.client.post(reverse("members:group_create"), {"name": "Pelanggan"})
        self.assertTrue(ContactGroup.objects.filter(owner=self.member, name="Pelanggan").exists())

    def test_delete_group_keeps_contacts(self):
        group = ContactGroup.objects.create(owner=self.member, name="Sementara")
        contact = Contact.objects.create(owner=self.member, phone="6281234567890")
        contact.groups.add(group)
        self.client.post(reverse("members:group_delete", args=[group.pk]))
        self.assertTrue(Contact.objects.filter(pk=contact.pk).exists())

    def test_list_shows_counts(self):
        group = ContactGroup.objects.create(owner=self.member, name="Kelas 5")
        for i, opted in enumerate([False, False, True]):
            c = Contact.objects.create(
                owner=self.member, phone=f"62812000000{i}", is_opted_out=opted
            )
            c.groups.add(group)
        response = self.client.get(reverse("members:group_list"))
        self.assertContains(response, "<strong>3</strong>", html=True)
        self.assertContains(response, "2 bisa dikirimi")


class TemplateViewTests(MemberAreaTestCase):
    def test_create_template(self):
        response = self.client.post(
            reverse("members:template_create"),
            {"name": "Pengingat", "body": "Halo {nama_depan}, jangan lupa besok."},
        )
        self.assertRedirects(response, reverse("members:template_list"))
        self.assertTrue(MessageTemplate.objects.filter(owner=self.member).exists())

    def test_unknown_variable_rejected(self):
        response = self.client.post(
            reverse("members:template_create"), {"name": "Promo", "body": "Diskon {harga}"}
        )
        self.assertContains(response, "Variabel tidak dikenal: {harga}")
        self.assertFalse(MessageTemplate.objects.exists())

    def test_preview_does_not_save(self):
        response = self.client.post(
            reverse("members:template_create"),
            {"name": "Sapaan", "body": "Halo {nama_depan}!", "action": "preview"},
        )
        self.assertContains(response, "Halo Siti!")
        self.assertFalse(MessageTemplate.objects.exists())

    def test_template_body_is_escaped(self):
        MessageTemplate.objects.create(
            owner=self.member, name="XSS", body="<script>alert(1)</script>"
        )
        response = self.client.get(reverse("members:template_list"))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")


class MemberHomeTests(MemberAreaTestCase):
    def test_home_shows_overview(self):
        Contact.objects.create(owner=self.member, phone="6281234567890")
        response = self.client.get(reverse("members:home"))
        self.assertEqual(response.context["overview"]["contacts"], 1)
        self.assertContains(response, reverse("members:contact_import"))
