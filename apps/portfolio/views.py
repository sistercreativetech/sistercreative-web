from django.views.generic import DetailView
from django_filters.views import FilterView

from . import selectors
from .filters import ProjectFilter


class ProjectListView(FilterView):
    filterset_class = ProjectFilter
    template_name = "pages/portfolio/list.html"
    context_object_name = "projects"
    paginate_by = 9

    def get_queryset(self):
        return selectors.published_projects()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        context["filter_querystring"] = params.urlencode()
        context["is_filtered"] = any(params.get(key) for key in ("q", "category", "tag"))
        return context


class ProjectDetailView(DetailView):
    template_name = "pages/portfolio/detail.html"
    context_object_name = "project"

    def get_queryset(self):
        return selectors.published_projects()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["related_projects"] = selectors.related_projects(self.object)
        return context
