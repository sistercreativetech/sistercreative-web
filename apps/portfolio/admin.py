from django.contrib import admin

from .models import Category, Project, Tag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "order"]
    list_editable = ["order"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "is_published", "is_featured", "order", "updated_at"]
    list_editable = ["is_published", "is_featured", "order"]
    list_filter = ["is_published", "is_featured", "category"]
    search_fields = ["title", "summary", "client_name"]
    prepopulated_fields = {"slug": ["title"]}
    filter_horizontal = ["tags"]
