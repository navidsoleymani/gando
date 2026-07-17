from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html


class BaseModelAdmin(admin.ModelAdmin):
    list_per_page = 10
    save_as = False
    save_on_top = False

    def __init__(self, *args, **kwargs):
        # Display Management
        self.available_field_in_display_list = True
        self.id_field_in_display_list = True
        self.created_dt_field_in_display_list = True
        self.updated_dt_field_in_display_list = True

        self.list_display = [] if not self.list_display else self.list_display
        self.list_display_links = [] if not self.list_display_links else self.list_display_links

        # Filter Fields Management
        self.available_field_in_filter_list = True
        self.created_dt_field_in_filter_list = True
        self.updated_dt_field_in_filter_list = True
        self.list_filter = [] if not self.list_filter else self.list_filter

        # Search Fields Management
        self.id_field_in_search_fields = True
        self.search_fields = [] if not self.search_fields else self.search_fields

        # Readonly Fields Management
        self.readonly_fields = [] if not self.readonly_fields else self.readonly_fields

        super().__init__(*args, **kwargs)

    _list_display = []

    @property
    def list_display(self):
        return self._list_display

    @list_display.setter
    def list_display(self, value):
        value = list(value)

        available_field_in_display_list = (
            self.available_field_in_display_list
            if hasattr(self, 'available_field_in_display_list') else False)
        id_field_in_display_list = (
            self.id_field_in_display_list
            if hasattr(self, 'id_field_in_display_list') else False)
        created_dt_field_in_display_list = (
            self.created_dt_field_in_display_list
            if hasattr(self,
                'created_dt_field_in_display_list') else False)
        updated_dt_field_in_display_list = (
            self.updated_dt_field_in_display_list
            if hasattr(self,
                'updated_dt_field_in_display_list') else False)

        tmp = [
            'id_'] if 'id' not in value and id_field_in_display_list else []
        tmp += value
        tmp += [
            'available_'] if 'available' not in value and available_field_in_display_list else []
        tmp += [
            'created_at_'] if 'created_dt' not in value and created_dt_field_in_display_list else []
        tmp += [
            'updated_at_'] if 'updated_dt' not in value and updated_dt_field_in_display_list else []

        self._list_display = tmp

    def available_(self, obj):
        if obj.available == 1:
            return format_html('<span style="color: green;">✓</span>', 1)
        else:
            return format_html('<span style="color: red;">✗</span>', 1)

    def id_(self, obj):
        return str(obj.id)[:8]

    def created_at_(self, obj):
        return obj.created_dt.strftime("%y/%m/%d %H:%M")

    def updated_at_(self, obj):
        return obj.updated_dt.strftime("%y/%m/%d %H:%M")

    _list_display_links = []

    @property
    def list_display_links(self):
        return self._list_display_links

    @list_display_links.setter
    def list_display_links(self, value):
        value = list(value)

        id_field_in_display_list = (
            self.id_field_in_display_list
            if hasattr(self, 'id_field_in_display_list') else False)

        tmp = [
            'id_'] if 'id' not in value and id_field_in_display_list else []
        tmp += value

        self._list_display_links = tmp

    image_fields_name_list = []

    def __set_image_fieldsets(self):
        tmp = []
        for i in self.image_fields_name_list:
            tmp += [
                (f'{i}_category', f'{i}_device_type',),
                (f'{i}_alt', f'{i}_src',),
                (f'{i}_width', f'{i}_height',),
                f'{i}_description',
                f'{i}_blurbase64',
            ]

        ret = [('Images', {'fields': tmp})] if tmp else []
        return ret

    def __get_image_read_only_fields(self):
        ret = []
        for i in self.image_fields_name_list:
            ret.append(f'{i}_blurbase64')
            ret.append(f'{i}_width')
            ret.append(f'{i}_height')
        return ret

    _fieldsets = []

    @property
    def fieldsets(self):
        return self._fieldsets

    @fieldsets.setter
    def fieldsets(self, value):
        tmp = [(_('Initial'), {'fields': [('available', 'id',)]})]
        tmp += value
        tmp += self.__set_image_fieldsets()
        tmp += [(
            _('Extra'), {
            'fields': [(
                "created_dt",
                "created_by",
                "created_by_user_agent_info",

                "updated_dt",
                "last_updated_by",
                "last_updated_by_user_agent_info",
            )]})]
        tmp += [(
            _('Deleted'), {
            'fields': [(
                "is_deleted",
                "deleted_dt",
                "deleted_by",
                "deleted_by_user_agent_info",
            )]})]
        tmp += [(
            _('Custom Settings'), {
            'fields': [(
                "server_side_settings",
                "client_side_settings",
            )]})]

        self._fieldsets = tmp

    _readonly_fields = []

    @property
    def readonly_fields(self):
        return self._readonly_fields

    @readonly_fields.setter
    def readonly_fields(self, value):
        value = list(value)

        tmp = value
        tmp += self.__get_image_read_only_fields()
        tmp += [
            'id'] if 'id' not in value else []

        tmp += [
            'created_dt'] if 'created_dt' not in value else []
        tmp += [
            "created_by"] if "created_by" not in value else []
        tmp += [
            "created_by_user_agent_info"] if "created_by_user_agent_info" not in value else []

        tmp += [
            'updated_dt'] if 'updated_dt' not in value else []
        tmp += [
            "last_updated_by"] if "last_updated_by" not in value else []
        tmp += [
            "last_updated_by_user_agent_info"] if "last_updated_by_user_agent_info" not in value else []

        tmp += [
            "deleted_dt"] if "deleted_dt" not in value else []
        tmp += [
            "deleted_by"] if "deleted_by" not in value else []
        tmp += [
            "deleted_by_user_agent_info"] if "deleted_by_user_agent_info" not in value else []

        self._readonly_fields = tmp

    _list_filter = []

    @property
    def list_filter(self):
        return self._list_filter

    @list_filter.setter
    def list_filter(self, value):
        value = list(value)

        available_field_in_filter_list = (
            self.available_field_in_filter_list
            if hasattr(self, 'available_field_in_filter_list') else False)
        created_dt_field_in_filter_list = (
            self.created_dt_field_in_filter_list
            if hasattr(self, 'created_dt_field_in_filter_list') else False)
        updated_dt_field_in_filter_list = (
            self.updated_dt_field_in_filter_list
            if hasattr(self, 'updated_dt_field_in_filter_list') else False)

        tmp = list(value)
        tmp += [
            'available'] if 'available' not in value and available_field_in_filter_list else []
        tmp += [
            'created_dt'] if 'created_dt' not in value and created_dt_field_in_filter_list else []
        tmp += [
            'updated_dt'] if 'updated_dt' not in value and updated_dt_field_in_filter_list else []

        tmp += [
            "deleted_dt"] if "deleted_dt" not in value else []
        tmp += [
            "is_deleted"] if "is_deleted" not in value else []

        self._list_filter = tmp

    _search_fields = []

    @property
    def search_fields(self):
        return self._search_fields

    @search_fields.setter
    def search_fields(self, value):
        value = list(value)

        id_field_in_search_fields = (
            self.id_field_in_search_fields if hasattr(self,
                'id_field_in_search_fields') else False)

        tmp = list(value)
        tmp += [
            'id'] if 'id' not in value and id_field_in_search_fields else []

        tmp += [
            "created_by"] if "created_by" not in value else []
        tmp += [
            "last_updated_by"] if "last_updated_by" not in value else []
        tmp += [
            "deleted_by"] if "deleted_by" not in value else []

        self._search_fields = tmp
