from __future__ import print_function

import json
import os
import re
import sys
import traceback

try:
    from scriptengine import *  # noqa: F401,F403 - injected by the CODESYS ScriptEngine
except Exception:
    # The script is intended to run inside CODESYS. Keeping this import optional makes
    # CPython syntax checks possible from the repository.
    pass

try:
    string_types = (basestring,)
except NameError:
    string_types = (str,)

try:
    text_type = unicode
except NameError:
    text_type = str


def _is_callable(value):
    try:
        return hasattr(value, "__call__")
    except Exception:
        return False


def _plain(value):
    if value is None:
        return None
    if isinstance(value, dict):
        converted = {}
        for key, item in value.items():
            converted[str(key)] = _plain(item)
        return converted
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, text_type):
        return value
    if isinstance(value, str):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.decode("cp1252", "replace")
    if isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _write_result(path, payload):
    text = json.dumps(_plain(payload), indent=2, sort_keys=True)
    if path:
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(path, "w") as handle:
            handle.write(text)
            handle.write("\n")
    print(text)


def _load_request():
    if len(sys.argv) < 2:
        raise Exception("Expected request JSON path in sys.argv[1].")

    request_path = sys.argv[1]
    with open(request_path, "r") as handle:
        request = json.load(handle)
    request["_request_path"] = request_path
    return request


def _norm_path(path):
    if not path:
        return None
    return os.path.normcase(os.path.abspath(path))


def _project_path(project):
    try:
        return str(project.path)
    except Exception:
        return None


def _get_primary_project(request):
    project = projects.primary
    if project is None:
        raise Exception("No primary project is open in the CODESYS instance running this script.")

    expected_path = request.get("project_path")
    if expected_path and request.get("require_project_path_match", True):
        actual = _project_path(project)
        if _norm_path(actual) != _norm_path(expected_path):
            raise Exception(
                "Primary project path mismatch. Expected '%s', got '%s'."
                % (expected_path, actual)
            )
    return project


def _object_name(obj):
    if obj is None:
        return None
    try:
        return str(obj.get_name(False))
    except TypeError:
        return str(obj.get_name())
    except Exception:
        path = _project_path(obj)
        if path:
            return os.path.basename(path)
        return str(obj)


def _children(obj, recursive):
    try:
        return list(obj.get_children(recursive))
    except TypeError:
        return list(obj.get_children())


def _find_child_by_name(container, name):
    for child in _children(container, False):
        if _object_name(child) == name:
            return child
    return None


def _find_descendant_by_name(container, name):
    if _object_name(container) == name:
        return container
    for child in _children(container, True):
        if _object_name(child) == name:
            return child
    return None


def _target_container(project, request):
    container_name = request.get("container")
    if container_name:
        found = _find_descendant_by_name(project, container_name)
        if found is None:
            raise Exception("Container '%s' was not found." % container_name)
        return found

    app = project.active_application
    if app is not None:
        return app
    return project


def _declaration_text(obj):
    if not obj.has_textual_declaration:
        raise Exception("Object '%s' has no textual declaration." % _object_name(obj))
    text = obj.textual_declaration.text
    if text is None:
        return ""
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def _set_declaration_text(obj, text):
    obj.textual_declaration.replace(new_text=text)


def _implementation_text(obj):
    if not obj.has_textual_implementation:
        raise Exception("Object '%s' has no textual implementation." % _object_name(obj))
    text = obj.textual_implementation.text
    if text is None:
        return ""
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def _decode_text(value):
    if value is None:
        return u""
    try:
        if isinstance(value, unicode):
            return value
    except NameError:
        return str(value)
    if isinstance(value, str):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.decode("cp1252", "replace")
    return unicode(value)


def _write_utf8(path, text):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "wb") as handle:
        handle.write(_decode_text(text).encode("utf-8"))


def _read_utf8(path):
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8")


def _export_object_text_files(request):
    project = _get_primary_project(request)
    name = request["object_name"]
    obj = _find_descendant_by_name(project, name)
    if obj is None:
        raise Exception("Object '%s' was not found." % name)

    output_dir = request["output_dir"]
    declaration_path = os.path.join(output_dir, name + ".decl.st")
    implementation_path = os.path.join(output_dir, name + ".impl.st")
    _write_utf8(declaration_path, _declaration_text(obj))
    _write_utf8(implementation_path, _implementation_text(obj))
    return {
        "project_path": _project_path(project),
        "object_name": name,
        "declaration_path": declaration_path,
        "implementation_path": implementation_path,
    }


def _update_object_text_files(request):
    project = _get_primary_project(request)
    name = request["object_name"]
    obj = _find_descendant_by_name(project, name)
    if obj is None:
        raise Exception("Object '%s' was not found." % name)

    declaration = _read_utf8(request["declaration_path"])
    implementation = _read_utf8(request["implementation_path"])
    changed_declaration = _decode_text(_declaration_text(obj)).strip() != declaration.strip()
    changed_implementation = _decode_text(_implementation_text(obj)).strip() != implementation.strip()
    if changed_declaration:
        _set_declaration_text(obj, declaration.strip())
    if changed_implementation:
        _set_implementation_text(obj, implementation.strip())

    saved = False
    if request.get("save", True) and (
        changed_declaration or changed_implementation or project.dirty
    ):
        project.save()
        saved = True
    return {
        "project_path": _project_path(project),
        "object_name": name,
        "changed_declaration": changed_declaration,
        "changed_implementation": changed_implementation,
        "saved": saved,
    }


def _set_implementation_text(obj, text):
    obj.textual_implementation.replace(new_text=text)


def _ensure_gvl(container, gvl_name):
    existing = _find_child_by_name(container, gvl_name)
    if existing is not None:
        return existing, False
    if not hasattr(container, "create_gvl"):
        raise Exception("Container '%s' cannot create GVL objects." % _object_name(container))
    return container.create_gvl(gvl_name), True


def _replace_existing_var_line(lines, var_name, var_type):
    pattern = re.compile(r"^(\s*)%s\s*:\s*[^;]+;(.*)$" % re.escape(var_name), re.IGNORECASE)
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            replacement = match.group(1) + "%s : %s;" % (var_name, var_type)
            if match.group(2):
                replacement += match.group(2)
            changed = replacement != line
            lines[index] = replacement
            return True, changed
    return False, False


def _insert_var_before_end_var(text, var_name, var_type):
    lines = text.split("\n")
    declaration = "    %s : %s;" % (var_name, var_type)
    for index, line in enumerate(lines):
        if line.strip().upper() == "END_VAR":
            if index > 0 and lines[index - 1].strip() == "":
                lines.insert(index, declaration)
            else:
                lines.insert(index, declaration)
            return "\n".join(lines)
    return "VAR_GLOBAL\n%s\nEND_VAR" % declaration


def _ensure_variable_in_gvl(gvl, var_name, var_type):
    text = _declaration_text(gvl).strip()
    if not text:
        new_text = "VAR_GLOBAL\n    %s : %s;\nEND_VAR" % (var_name, var_type)
        _set_declaration_text(gvl, new_text)
        return True

    lines = text.split("\n")
    found, changed = _replace_existing_var_line(lines, var_name, var_type)
    if found:
        if changed:
            _set_declaration_text(gvl, "\n".join(lines))
        return changed

    new_text = _insert_var_before_end_var(text, var_name, var_type)
    if new_text != text:
        _set_declaration_text(gvl, new_text)
        return True
    return False


def _extract_uint_constant(text, const_name):
    pattern = re.compile(
        r"\b%s\s*:\s*UINT\s*:=\s*(\d+)\s*;" % re.escape(const_name),
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        raise Exception("UINT constant '%s' was not found." % const_name)
    return int(match.group(1))


def _create_pou_object(
    container,
    name,
    pou_type,
    return_type="",
    base_type="",
    interfaces="",
):
    if not hasattr(container, "create_pou"):
        raise Exception("Container '%s' cannot create POU objects." % _object_name(container))
    return container.create_pou(
        name,
        pou_type,
        None,
        str(return_type or ""),
        str(base_type or ""),
        str(interfaces or ""),
    )


def _ensure_function_block(container, fb_name):
    existing = _find_child_by_name(container, fb_name)
    if existing is not None:
        return existing, False
    return _create_pou_object(container, fb_name, PouType.FunctionBlock), True


def _safe_texts(obj):
    result = {}
    try:
        if obj.has_textual_declaration:
            result["declaration"] = _declaration_text(obj)
    except Exception:
        pass
    try:
        if obj.has_textual_implementation:
            result["implementation"] = _implementation_text(obj)
    except Exception:
        pass
    return result


def _object_summary(obj, include_text=False):
    result = {
        "name": _object_name(obj),
    }
    for prop in ["is_folder", "has_textual_declaration", "has_textual_implementation", "is_application"]:
        try:
            result[prop] = bool(getattr(obj, prop))
        except Exception:
            pass
    try:
        result["type"] = str(obj.type)
    except Exception:
        pass
    try:
        result["guid"] = str(obj.guid)
    except Exception:
        pass
    try:
        result["children"] = [_object_name(child) for child in _children(obj, False)]
    except Exception:
        pass
    if include_text:
        result.update(_safe_texts(obj))
    return result


def _tree_summary(obj, depth, include_text):
    result = _object_summary(obj, include_text)
    if depth <= 0:
        return result
    children = []
    try:
        for child in _children(obj, False):
            children.append(_tree_summary(child, depth - 1, include_text))
    except Exception:
        pass
    result["child_objects"] = children
    return result


def _set_optional_texts(obj, request):
    changed_declaration = False
    changed_implementation = False

    declaration = request.get("declaration")
    if declaration is not None:
        declaration = str(declaration).replace("\r\n", "\n").replace("\r", "\n").strip()
        changed_declaration = _declaration_text(obj).strip() != declaration
        if changed_declaration:
            _set_declaration_text(obj, declaration)

    implementation = request.get("implementation")
    if implementation is not None:
        implementation = str(implementation).replace("\r\n", "\n").replace("\r", "\n").strip()
        changed_implementation = _implementation_text(obj).strip() != implementation
        if changed_implementation:
            _set_implementation_text(obj, implementation)

    return changed_declaration, changed_implementation


def _dut_type(name):
    normalized = str(name or "Structure").lower()
    mapping = {
        "structure": DutType.Structure,
        "struct": DutType.Structure,
        "enumeration": DutType.Enumeration,
        "enum": DutType.Enumeration,
        "alias": DutType.Alias,
        "union": DutType.Union,
        "enumerationwithtextlist": DutType.EnumerationWithTextList,
        "enum_text": DutType.EnumerationWithTextList,
    }
    if normalized not in mapping:
        raise Exception("Unsupported DUT type '%s'." % name)
    return mapping[normalized]


def _create_object(container, kind, name, request):
    normalized = str(kind).lower().replace("-", "_")
    if normalized == "folder":
        return container.create_folder(name)
    if normalized == "gvl":
        return container.create_gvl(name)
    if normalized in ["persistent_gvl", "persistentvars", "persistent_variables"]:
        return container.create_persistentvars(name)
    if normalized == "program":
        return _create_pou_object(container, name, PouType.Program)
    if normalized in ["function_block", "fb"]:
        return _create_pou_object(
            container,
            name,
            PouType.FunctionBlock,
            base_type=request.get("base_type", ""),
            interfaces=request.get("interfaces", ""),
        )
    if normalized == "function":
        return_type = request.get("return_type")
        if not return_type:
            raise Exception("Creating a function requires 'return_type'.")
        return _create_pou_object(
            container,
            name,
            PouType.Function,
            return_type=return_type,
        )
    if normalized == "dut":
        return container.create_dut(
            name,
            type=_dut_type(request.get("dut_type", "Structure")),
            baseType=request.get("base_type"),
        )
    if normalized == "interface":
        return container.create_interface(name, request.get("base_interfaces", "__System.IQueryInterface"))
    if normalized == "method":
        return container.create_method(name, return_type=request.get("return_type"))
    if normalized == "property":
        return container.create_property(name, return_type=request.get("return_type", "INT"))
    if normalized == "action":
        return container.create_action(name)
    if normalized == "transition":
        return container.create_transition(name)
    raise Exception("Unsupported object kind '%s'." % kind)


def _ensure_object(container, kind, name, request):
    existing = _find_child_by_name(container, name)
    if existing is not None:
        return existing, False
    return _create_object(container, kind, name, request), True


def _inspect(request):
    project = _get_primary_project(request)
    try:
        app = project.active_application
    except Exception:
        app = None
    return {
        "project_path": _project_path(project),
        "project_dirty": bool(project.dirty),
        "active_application": _object_name(app) if app is not None else None,
        "top_level_objects": [_object_name(child) for child in _children(project, False)],
    }


def _inspect_tree(request):
    project = _get_primary_project(request)
    root_name = request.get("root")
    if root_name:
        root = _find_descendant_by_name(project, root_name)
        if root is None:
            raise Exception("Root object '%s' was not found." % root_name)
    else:
        root = project
    return _tree_summary(root, int(request.get("depth", 3)), bool(request.get("include_text", False)))


def _read_object(request):
    project = _get_primary_project(request)
    name = request["object_name"]
    obj = _find_descendant_by_name(project, name)
    if obj is None:
        raise Exception("Object '%s' was not found." % name)
    return _object_summary(obj, include_text=True)


def _safe_attr_value(obj, attr_name):
    try:
        value = getattr(obj, attr_name)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }

    try:
        callable_value = _is_callable(value)
    except Exception:
        callable_value = False

    result = {
        "ok": True,
        "type": str(type(value)),
        "callable": bool(callable_value),
    }
    if callable_value:
        result["repr"] = str(value)
        try:
            doc = getattr(value, "__doc__")
            if doc:
                result["doc"] = str(doc)
        except Exception:
            pass
        try:
            result["dir"] = _limited_dir(value)
        except Exception:
            pass
    if not callable_value:
        result["value"] = _plain(value)
    return result


def _describe_object(request):
    project = _get_primary_project(request)
    name = request["object_name"]
    obj = _find_descendant_by_name(project, name)
    if obj is None:
        raise Exception("Object '%s' was not found." % name)

    names = []
    try:
        names = sorted([str(item) for item in dir(obj)])
    except Exception:
        names = []

    requested_attrs = request.get("attrs", [])
    attrs = {}
    for attr_name in requested_attrs:
        attrs[str(attr_name)] = _safe_attr_value(obj, str(attr_name))

    return {
        "object": _object_summary(obj, include_text=False),
        "python_type": str(type(obj)),
        "dir": names,
        "attrs": attrs,
    }


def _limited_dir(value):
    try:
        return sorted([str(item) for item in dir(value)])
    except Exception:
        return []


def _call_noargs(value, method_name):
    try:
        method = getattr(value, method_name)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }
    try:
        result = method()
        return {
            "ok": True,
            "value": _plain(result),
            "type": str(type(result)),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }


def _describe_value(value, max_items=40):
    result = {
        "type": str(type(value)),
        "dir": _limited_dir(value),
        "repr": str(value),
    }

    for method_name in ["Count", "count", "get_count", "is_enabled", "get_name", "get_children"]:
        result[method_name] = _call_noargs(value, method_name)

    try:
        items = []
        for item in value:
            if len(items) >= max_items:
                break
            item_details = {
                "type": str(type(item)),
                "repr": str(item),
                "dir": _limited_dir(item),
                "safe_attrs": {
                    "name": _safe_attr_value(item, "name"),
                    "id": _safe_attr_value(item, "id"),
                    "identifier": _safe_attr_value(item, "identifier"),
                    "visible_name": _safe_attr_value(item, "visible_name"),
                    "description": _safe_attr_value(item, "description"),
                    "value": _safe_attr_value(item, "value"),
                    "default_value": _safe_attr_value(item, "default_value"),
                    "allowed_values": _safe_attr_value(item, "allowed_values"),
                    "param_type": _safe_attr_value(item, "param_type"),
                    "iec_type": _safe_attr_value(item, "iec_type"),
                    "type_string": _safe_attr_value(item, "type_string"),
                    "offline_access_rights": _safe_attr_value(item, "offline_access_rights"),
                    "online_access_rights": _safe_attr_value(item, "online_access_rights"),
                    "can_access_online": _safe_attr_value(item, "can_access_online"),
                    "downloaded_with_ioconfig": _safe_attr_value(item, "downloaded_with_ioconfig"),
                    "guid": _safe_attr_value(item, "guid"),
                    "type": _safe_attr_value(item, "type"),
                    "flags": _safe_attr_value(item, "flags"),
                    "connector_id": _safe_attr_value(item, "connector_id"),
                    "connector_role": _safe_attr_value(item, "connector_role"),
                    "interface_name": _safe_attr_value(item, "interface_name"),
                    "host_path": _safe_attr_value(item, "host_path"),
                    "module_type": _safe_attr_value(item, "module_type"),
                    "io_always_mapping": _safe_attr_value(item, "io_always_mapping"),
                    "is_explicit": _safe_attr_value(item, "is_explicit"),
                    "is_enabled": _safe_attr_value(item, "is_enabled"),
                    "enable": _safe_attr_value(item, "enable"),
                    "disable": _safe_attr_value(item, "disable"),
                },
            }
            for nested_name in ["host_parameters", "driver_info", "additional_interfaces"]:
                try:
                    nested = getattr(item, nested_name)
                    item_details[nested_name] = _describe_value(nested, max_items=12)
                except Exception as exc:
                    item_details[nested_name] = {
                        "error": str(exc),
                    }
            items.append({
                "details": item_details,
            })
        result["iterable"] = True
        result["items"] = items
    except Exception as exc:
        result["iterable"] = False
        result["iteration_error"] = str(exc)

    return result


def _describe_device_details(request):
    project = _get_primary_project(request)
    name = request["object_name"]
    obj = _find_descendant_by_name(project, name)
    if obj is None:
        raise Exception("Object '%s' was not found." % name)

    details = {
        "object": _object_summary(obj, include_text=False),
        "is_enabled": _call_noargs(obj, "is_enabled"),
    }
    for attr_name in ["connectors", "device_parameters"]:
        try:
            value = getattr(obj, attr_name)
            details[attr_name] = _describe_value(value)
        except Exception as exc:
            details[attr_name] = {
                "error": str(exc),
            }
    return details


def _export_object_xml(request):
    project = _get_primary_project(request)
    name = request["object_name"]
    obj = _find_descendant_by_name(project, name)
    if obj is None:
        raise Exception("Object '%s' was not found." % name)

    destination = request["destination"]
    recursive = bool(request.get("recursive", False))
    export_folder_structure = bool(request.get("export_folder_structure", True))
    declarations_as_plaintext = bool(request.get("declarations_as_plaintext", True))

    directory = os.path.dirname(destination)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)

    result = obj.export_xml(
        destination,
        recursive,
        export_folder_structure,
        declarations_as_plaintext,
    )
    return {
        "project_path": _project_path(project),
        "object_name": _object_name(obj),
        "destination": destination,
        "recursive": recursive,
        "export_folder_structure": export_folder_structure,
        "declarations_as_plaintext": declarations_as_plaintext,
        "result": _plain(result),
    }


def _conflict_resolve(value):
    normalized = str(value or "Replace").lower()
    mapping = {
        "copy": ConflictResolve.Copy,
        "replace": ConflictResolve.Replace,
        "skip": ConflictResolve.Skip,
    }
    if normalized not in mapping:
        raise Exception("Unsupported XML import conflict resolve '%s'." % value)
    return mapping[normalized]


def _call_import_xml(target, conflict_resolve, source, import_folder_structure):
    try:
        return target.import_xml(conflict_resolve, source, import_folder_structure)
    except TypeError:
        return target.import_xml(conflict_resolve, source)


def _import_object_xml(request):
    project = _get_primary_project(request)
    source = request["source"]
    if not os.path.isfile(source):
        raise Exception("XML import source '%s' was not found." % source)

    target = _target_container(project, request)
    import_folder_structure = bool(request.get("import_folder_structure", True))
    conflict_name = request.get("conflict_resolve", "Replace")
    conflict = _conflict_resolve(conflict_name)

    backup_destination = request.get("backup_destination")
    backup_object_name = request.get("backup_object_name")
    backup_result = None
    if backup_destination:
        backup_object = target
        if backup_object_name:
            backup_object = _find_descendant_by_name(project, backup_object_name)
            if backup_object is None:
                raise Exception("Backup object '%s' was not found." % backup_object_name)

        directory = os.path.dirname(backup_destination)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)

        backup_result = backup_object.export_xml(
            backup_destination,
            bool(request.get("backup_recursive", True)),
            bool(request.get("backup_export_folder_structure", True)),
            bool(request.get("backup_declarations_as_plaintext", True)),
        )

    import_result = _call_import_xml(target, conflict, source, import_folder_structure)

    saved = False
    if request.get("save", True):
        project.save()
        saved = True

    return {
        "project_path": _project_path(project),
        "source": source,
        "container": _object_name(target),
        "conflict_resolve": str(conflict_name),
        "import_folder_structure": import_folder_structure,
        "backup_object_name": backup_object_name,
        "backup_destination": backup_destination,
        "backup_result": _plain(backup_result),
        "import_result": _plain(import_result),
        "saved": saved,
    }


def _describe_script_symbol(request):
    name = request["symbol_name"]
    if name not in globals():
        return {
            "symbol_name": name,
            "found": False,
        }

    value = globals()[name]
    attrs = {}
    for attr_name in _limited_dir(value):
        if attr_name.startswith("_"):
            continue
        attrs[attr_name] = _safe_attr_value(value, attr_name)
    return {
        "symbol_name": name,
        "found": True,
        "type": str(type(value)),
        "repr": str(value),
        "dir": _limited_dir(value),
        "attrs": attrs,
    }


def _parameter_summary(parameter, depth):
    attr_names = [
        "id",
        "identifier",
        "name",
        "visible_name",
        "description",
        "value",
        "default_value",
        "type_string",
        "param_type",
        "iec_type",
        "section",
        "value_index",
        "bit_size",
        "channel_type",
        "base_type",
        "is_mappable_io",
        "user_comment",
        "offline_access_rights",
        "online_access_rights",
        "can_access_online",
        "downloaded_with_ioconfig",
    ]
    result = {
        "python_type": str(type(parameter)),
        "attrs": {},
        "children": [],
    }
    for attr_name in attr_names:
        result["attrs"][attr_name] = _safe_attr_value(parameter, attr_name)

    try:
        result["io_mapping"] = _io_mapping_summary(parameter.io_mapping)
    except Exception as exc:
        result["io_mapping"] = {
            "ok": False,
            "error": str(exc),
        }

    if depth > 0:
        try:
            for child in parameter:
                result["children"].append(_parameter_summary(child, depth - 1))
        except Exception:
            pass
    return result


def _io_mapping_summary(mapping):
    attr_names = [
        "Id",
        "variable",
        "default_variable",
        "mapping_creates_variable",
        "maps_to_existing_variable",
        "automatic_iec_address",
        "manual_iec_address",
    ]
    result = {
        "ok": True,
        "python_type": str(type(mapping)),
        "attrs": {},
    }
    for attr_name in attr_names:
        result["attrs"][attr_name] = _safe_attr_value(mapping, attr_name)
    return result


def _attr_payload_value(payload):
    if not isinstance(payload, dict):
        return None
    if not payload.get("ok", False):
        return None
    if payload.get("callable", False):
        return None
    if "value" not in payload:
        return None
    return payload.get("value")


def _get_plain_attr(obj, attr_name):
    return _attr_payload_value(_safe_attr_value(obj, attr_name))


def _parameter_record(parameter, depth, element_path):
    attr_names = [
        "id",
        "identifier",
        "name",
        "value",
        "is_mappable_io",
        "user_comment",
        "offline_access_rights",
    ]
    attrs = {}
    for attr_name in attr_names:
        attrs[attr_name] = _safe_attr_value(parameter, attr_name)

    record = {
        "id": _attr_payload_value(attrs["id"]),
        "identifier": _attr_payload_value(attrs["identifier"]),
        "name": _attr_payload_value(attrs["name"]),
        "path": [str(item) for item in element_path],
        "attrs": attrs,
        "children": [],
    }

    if _attr_payload_value(attrs["is_mappable_io"]):
        try:
            record["io_mapping"] = _io_mapping_summary(parameter.io_mapping)
        except Exception as exc:
            record["io_mapping"] = {
                "ok": False,
                "error": str(exc),
            }

    if depth > 0:
        try:
            for child in parameter:
                child_identifier = _get_plain_attr(child, "identifier")
                if child_identifier is None:
                    child_identifier = _get_plain_attr(child, "name")
                if child_identifier is None:
                    child_identifier = _get_plain_attr(child, "id")
                child_path = list(element_path)
                if child_identifier is not None:
                    child_path.append(str(child_identifier))
                record["children"].append(_parameter_record(child, depth - 1, child_path))
        except Exception:
            pass
    return record


def _parameter_set_records(parameters, depth):
    records = []
    try:
        for parameter in parameters:
            records.append(_parameter_record(parameter, depth, []))
    except Exception:
        pass
    return records


def _export_device_internal_config(request):
    project = _get_primary_project(request)
    device_names = request.get("device_names", [])
    if not device_names:
        raise Exception("export_device_internal_config requires a non-empty 'device_names' list.")

    depth = int(request.get("depth", 16))
    devices = []
    for name in device_names:
        obj = _find_descendant_by_name(project, str(name))
        if obj is None:
            devices.append({
                "name": str(name),
                "found": False,
            })
            continue

        connectors = []
        for connector in obj.connectors:
            connector_record = {
                "connector_id": _plain(connector.connector_id),
                "connector_role": _plain(connector.connector_role),
                "interface_name": _plain(connector.interface_name),
                "module_type": _plain(connector.module_type),
                "host_path": _plain(connector.host_path),
                "io_always_mapping": _safe_attr_value(connector, "io_always_mapping"),
                "parameters": _parameter_set_records(connector.host_parameters, depth),
            }
            connectors.append(connector_record)

        device_parameters = []
        try:
            device_parameters = _parameter_set_records(obj.device_parameters, depth)
        except Exception:
            device_parameters = []

        devices.append({
            "name": _object_name(obj),
            "found": True,
            "object": _object_summary(obj, include_text=False),
            "connectors": connectors,
            "device_parameters": device_parameters,
        })

    return {
        "project_path": _project_path(project),
        "devices": devices,
    }


def _coerce_like(current, value):
    if isinstance(current, bool):
        if isinstance(value, string_types):
            return value.strip().lower() in ["1", "true", "yes"]
        return bool(value)
    return value


def _set_field(target, attr_name, value, changes, skipped, errors, context, copy_readonly):
    if value is None:
        return
    try:
        before = getattr(target, attr_name)
    except Exception as exc:
        skipped.append({
            "context": context,
            "field": attr_name,
            "reason": "missing target field: " + str(exc),
        })
        return

    if attr_name == "value" and not copy_readonly:
        access = str(_get_plain_attr(target, "offline_access_rights"))
        if access != "ReadWrite":
            if str(before) != str(value):
                skipped.append({
                    "context": context,
                    "field": attr_name,
                    "reason": "target offline access is " + access,
                    "source_value": value,
                    "target_value": _plain(before),
                })
            return

    requested = _coerce_like(before, value)
    if str(before) == str(requested):
        return

    try:
        setattr(target, attr_name, requested)
        after = getattr(target, attr_name)
        changes.append({
            "context": context,
            "field": attr_name,
            "before": _plain(before),
            "after": _plain(after),
        })
    except Exception as exc:
        errors.append({
            "context": context,
            "field": attr_name,
            "error": str(exc),
        })


def _find_child_parameter(parent, record):
    identifier = record.get("identifier")
    if identifier is not None:
        try:
            return parent[str(identifier)]
        except Exception:
            pass

    parameter_id = record.get("id")
    if parameter_id is not None:
        try:
            return parent.by_id(int(parameter_id))
        except Exception:
            pass

    name = record.get("name")
    try:
        for child in parent:
            if parameter_id is not None and str(_get_plain_attr(child, "id")) == str(parameter_id):
                return child
            if identifier is not None and str(_get_plain_attr(child, "identifier")) == str(identifier):
                return child
            if name is not None and str(_get_plain_attr(child, "name")) == str(name):
                return child
    except Exception:
        pass
    return None


def _find_top_parameter(parameters, record):
    parameter_id = record.get("id")
    if parameter_id is not None:
        try:
            return parameters.by_id(int(parameter_id))
        except Exception:
            pass

    identifier = record.get("identifier")
    name = record.get("name")
    try:
        for parameter in parameters:
            if parameter_id is not None and str(_get_plain_attr(parameter, "id")) == str(parameter_id):
                return parameter
            if identifier is not None and str(_get_plain_attr(parameter, "identifier")) == str(identifier):
                return parameter
            if name is not None and str(_get_plain_attr(parameter, "name")) == str(name):
                return parameter
    except Exception:
        pass
    return None


def _record_attr(record, attr_name):
    return _attr_payload_value(record.get("attrs", {}).get(attr_name))


def _apply_mapping_record(target_element, record, mapping_fields, changes, skipped, errors, context, copy_readonly):
    source_mapping = record.get("io_mapping", {})
    if not source_mapping.get("ok", False):
        return

    source_attrs = source_mapping.get("attrs", {})
    has_value = False
    for field_name in mapping_fields:
        if _attr_payload_value(source_attrs.get(field_name)) is not None:
            has_value = True
            break
    if not has_value:
        return

    try:
        target_mapping = target_element.io_mapping
    except Exception as exc:
        skipped.append({
            "context": context,
            "field": "io_mapping",
            "reason": "target has no io_mapping: " + str(exc),
        })
        return

    if target_mapping is None:
        skipped.append({
            "context": context,
            "field": "io_mapping",
            "reason": "target io_mapping is None",
        })
        return

    for field_name in mapping_fields:
        source_value = _attr_payload_value(source_attrs.get(field_name))
        if source_value is None:
            continue
        _set_field(
            target_mapping,
            field_name,
            source_value,
            changes,
            skipped,
            errors,
            context + ".io_mapping",
            copy_readonly,
        )


def _apply_parameter_record(target_element, record, parameter_fields, mapping_fields, changes, skipped, errors, context, copy_readonly):
    for field_name in parameter_fields:
        source_value = _record_attr(record, field_name)
        if source_value is None:
            continue
        _set_field(
            target_element,
            field_name,
            source_value,
            changes,
            skipped,
            errors,
            context,
            copy_readonly,
        )

    _apply_mapping_record(
        target_element,
        record,
        mapping_fields,
        changes,
        skipped,
        errors,
        context,
        copy_readonly,
    )

    for child_record in record.get("children", []):
        child = _find_child_parameter(target_element, child_record)
        child_context = context + "/" + str(child_record.get("identifier") or child_record.get("name") or child_record.get("id"))
        if child is None:
            skipped.append({
                "context": child_context,
                "field": "parameter",
                "reason": "target child parameter not found",
            })
            continue
        _apply_parameter_record(
            child,
            child_record,
            parameter_fields,
            mapping_fields,
            changes,
            skipped,
            errors,
            child_context,
            copy_readonly,
        )


def _apply_parameter_records(parameters, records, parameter_fields, mapping_fields, changes, skipped, errors, context, copy_readonly):
    for record in records:
        target = _find_top_parameter(parameters, record)
        record_context = context + "/" + str(record.get("identifier") or record.get("name") or record.get("id"))
        if target is None:
            skipped.append({
                "context": record_context,
                "field": "parameter",
                "reason": "target top-level parameter not found",
            })
            continue
        _apply_parameter_record(
            target,
            record,
            parameter_fields,
            mapping_fields,
            changes,
            skipped,
            errors,
            record_context,
            copy_readonly,
        )


def _import_device_internal_config(request):
    project = _get_primary_project(request)
    payload = request.get("config")
    if not isinstance(payload, dict):
        raise Exception("import_device_internal_config requires a 'config' object from export_device_internal_config.")

    parameter_fields = request.get("parameter_fields", ["value", "user_comment"])
    mapping_fields = request.get("mapping_fields", [
        "variable",
        "default_variable",
        "mapping_creates_variable",
        "maps_to_existing_variable",
        "manual_iec_address",
    ])
    connector_fields = request.get("connector_fields", ["io_always_mapping"])
    copy_readonly = bool(request.get("copy_readonly", False))

    changes = []
    skipped = []
    errors = []

    for device_record in payload.get("devices", []):
        if not device_record.get("found", False):
            skipped.append({
                "context": str(device_record.get("name")),
                "field": "device",
                "reason": "source device was not found",
            })
            continue
        device_name = str(device_record.get("name"))
        obj = _find_descendant_by_name(project, device_name)
        if obj is None:
            skipped.append({
                "context": device_name,
                "field": "device",
                "reason": "target device not found",
            })
            continue

        for connector_record in device_record.get("connectors", []):
            connector_id = connector_record.get("connector_id")
            connector_context = device_name + ".connector[" + str(connector_id) + "]"
            try:
                connector = obj.connectors.by_id(int(connector_id))
            except Exception as exc:
                skipped.append({
                    "context": connector_context,
                    "field": "connector",
                    "reason": "target connector not found: " + str(exc),
                })
                continue

            for field_name in connector_fields:
                source_value = _attr_payload_value(connector_record.get(field_name))
                if source_value is None:
                    continue
                _set_field(
                    connector,
                    field_name,
                    source_value,
                    changes,
                    skipped,
                    errors,
                    connector_context,
                    copy_readonly,
                )

            _apply_parameter_records(
                connector.host_parameters,
                connector_record.get("parameters", []),
                parameter_fields,
                mapping_fields,
                changes,
                skipped,
                errors,
                connector_context,
                copy_readonly,
            )

        try:
            _apply_parameter_records(
                obj.device_parameters,
                device_record.get("device_parameters", []),
                parameter_fields,
                mapping_fields,
                changes,
                skipped,
                errors,
                device_name + ".device_parameters",
                copy_readonly,
            )
        except Exception as exc:
            if device_record.get("device_parameters", []):
                skipped.append({
                    "context": device_name + ".device_parameters",
                    "field": "device_parameters",
                    "reason": str(exc),
                })

    saved = False
    if request.get("save", True):
        project.save()
        saved = True

    report_limit = int(request.get("report_limit", 200))
    return {
        "project_path": _project_path(project),
        "source_project_path": payload.get("project_path"),
        "change_count": len(changes),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "changes": changes[:report_limit],
        "skipped": skipped[:report_limit],
        "errors": errors[:report_limit],
        "report_limit": report_limit,
        "saved": saved,
    }


def _describe_device_parameters(request):
    project = _get_primary_project(request)
    name = request["object_name"]
    obj = _find_descendant_by_name(project, name)
    if obj is None:
        raise Exception("Object '%s' was not found." % name)

    depth = int(request.get("depth", 4))
    connectors = []
    for connector in obj.connectors:
        connector_result = {
            "connector_id": _plain(connector.connector_id),
            "connector_role": _plain(connector.connector_role),
            "interface_name": _plain(connector.interface_name),
            "module_type": _plain(connector.module_type),
            "host_path": _plain(connector.host_path),
            "parameters": [],
        }
        for parameter in connector.host_parameters:
            connector_result["parameters"].append(_parameter_summary(parameter, depth))
        connectors.append(connector_result)

    return {
        "object": _object_summary(obj, include_text=False),
        "connectors": connectors,
    }


def _describe_device_driver_info(request):
    project = _get_primary_project(request)
    name = request["object_name"]
    obj = _find_descendant_by_name(project, name)
    if obj is None:
        raise Exception("Object '%s' was not found." % name)

    attr_names = [
        "enable_diagnosis",
        "can_set_io_application",
        "io_application",
        "always_update_variables",
        "update_ios_while_in_stop",
        "show_io_warnings_as_errors",
        "generate_force_variables",
        "behaviour_for_outputs_on_stop",
        "user_program_for_stop_reset_behaviour",
        "RequiredLibs",
    ]
    device_driver_info = obj.driver_info
    device_attrs = {}
    for attr_name in attr_names:
        device_attrs[attr_name] = _safe_attr_value(device_driver_info, attr_name)

    connectors = []
    for connector in obj.connectors:
        driver_info = connector.driver_info
        attrs = {}
        for attr_name in attr_names:
            attrs[attr_name] = _safe_attr_value(driver_info, attr_name)
        connectors.append({
            "connector_id": _plain(connector.connector_id),
            "connector_role": _plain(connector.connector_role),
            "interface_name": _plain(connector.interface_name),
            "driver_info_type": str(type(driver_info)),
            "driver_info_dir": _limited_dir(driver_info),
            "attrs": attrs,
        })

    return {
        "object": _object_summary(obj, include_text=False),
        "device_driver_info": {
            "driver_info_type": str(type(device_driver_info)),
            "driver_info_dir": _limited_dir(device_driver_info),
            "attrs": device_attrs,
        },
        "connectors": connectors,
    }


def _set_device_parameter_value(request):
    project = _get_primary_project(request)
    name = request["object_name"]
    obj = _find_descendant_by_name(project, name)
    if obj is None:
        raise Exception("Object '%s' was not found." % name)

    connector_id = int(request["connector_id"])
    parameter_id = int(request["parameter_id"])
    connector = obj.connectors.by_id(connector_id)
    parameter = connector.host_parameters.by_id(parameter_id)
    element = parameter
    element_path = request.get("element_path", [])
    for identifier in element_path:
        element = element[str(identifier)]

    before = str(element.value)
    requested_value = str(request["value"])
    element.value = requested_value
    after = str(element.value)
    if after != requested_value:
        raise Exception(
            "Device parameter value did not persist. Requested '%s', got '%s'."
            % (requested_value, after)
        )

    saved = False
    if request.get("save", True):
        project.save()
        saved = True

    return {
        "project_path": _project_path(project),
        "object_name": _object_name(obj),
        "connector_id": connector_id,
        "parameter_id": parameter_id,
        "element_path": [str(item) for item in element_path],
        "value_before": before,
        "value_after": after,
        "changed": before != after,
        "saved": saved,
    }


def _set_device_diagnosis_enabled(request):
    project = _get_primary_project(request)
    name = request["object_name"]
    obj = _find_descendant_by_name(project, name)
    if obj is None:
        raise Exception("Object '%s' was not found." % name)

    enabled = bool(request.get("enabled", True))
    requested_connector_id = request.get("connector_id")
    results = []

    if requested_connector_id is None:
        driver_info = obj.driver_info
        before = bool(driver_info.enable_diagnosis)
        driver_info.enable_diagnosis = enabled
        after = bool(driver_info.enable_diagnosis)
        if after != enabled:
            raise Exception(
                "Device diagnosis setting did not persist on '%s'." % name
            )
        results.append({
            "scope": "device",
            "enabled_before": before,
            "enabled_after": after,
            "changed": before != after,
        })

    for connector in obj.connectors if requested_connector_id is not None else []:
        connector_id = int(connector.connector_id)
        if requested_connector_id is not None and connector_id != int(requested_connector_id):
            continue

        driver_info = connector.driver_info
        before = bool(driver_info.enable_diagnosis)
        driver_info.enable_diagnosis = enabled
        after = bool(driver_info.enable_diagnosis)
        if after != enabled:
            raise Exception(
                "Device diagnosis setting did not persist on '%s' connector %s."
                % (name, connector_id)
            )
        results.append({
            "connector_id": connector_id,
            "enabled_before": before,
            "enabled_after": after,
            "changed": before != after,
        })

    if not results:
        raise Exception(
            "No matching connector was found on '%s'." % name
        )

    saved = False
    if request.get("save", True):
        project.save()
        saved = True

    return {
        "project_path": _project_path(project),
        "object_name": _object_name(obj),
        "enabled": enabled,
        "connectors": results,
        "saved": saved,
    }


def _delete_objects(request):
    project = _get_primary_project(request)
    object_names = request.get("object_names", [])
    if not object_names:
        raise Exception("delete_objects requires a non-empty 'object_names' list.")

    results = []
    for name in object_names:
        obj = _find_descendant_by_name(project, str(name))
        if obj is None:
            results.append({"name": str(name), "deleted": False, "reason": "not found"})
            continue
        actual_name = _object_name(obj)
        obj.remove()
        results.append({"name": actual_name, "deleted": True})

    saved = False
    if request.get("save", True):
        project.save()
        saved = True

    return {
        "project_path": _project_path(project),
        "objects": results,
        "saved": saved,
    }


def _add_gvl_var(request):
    project = _get_primary_project(request)
    container = _target_container(project, request)
    gvl_name = request.get("gvl_name", "GVL")
    var_name = request["var_name"]
    var_type = request.get("var_type", "BOOL").upper()

    gvl, created_gvl = _ensure_gvl(container, gvl_name)
    changed_var = _ensure_variable_in_gvl(gvl, var_name, var_type)

    saved = False
    if request.get("save", True) and (created_gvl or changed_var or project.dirty):
        project.save()
        saved = True

    return {
        "project_path": _project_path(project),
        "container": _object_name(container),
        "gvl_name": _object_name(gvl),
        "created_gvl": created_gvl,
        "changed_variable": changed_var,
        "saved": saved,
        "declaration": _declaration_text(gvl),
    }


def _upsert_object(request):
    project = _get_primary_project(request)
    container = _target_container(project, request)
    kind = request["object_kind"]
    name = request["object_name"]

    obj, created = _ensure_object(container, kind, name, request)
    changed_declaration, changed_implementation = _set_optional_texts(obj, request)

    saved = False
    if request.get("save", True) and (created or changed_declaration or changed_implementation or project.dirty):
        project.save()
        saved = True

    result = {
        "project_path": _project_path(project),
        "container": _object_name(container),
        "object": _object_summary(obj, include_text=True),
        "created": created,
        "changed_declaration": changed_declaration,
        "changed_implementation": changed_implementation,
        "saved": saved,
    }
    return result


def _visual_element_type(name):
    normalized = str(name or "").replace(" ", "").replace("-", "").replace("_", "").lower()
    for candidate in [
        "Rectangle",
        "RoundedRectangle",
        "Ellipse",
        "Polygon",
        "Polyline",
        "BezierCurve",
        "Line",
        "Button",
        "Image",
        "Pie",
        "Frame",
        "Lamp",
        "RotarySwitch",
        "ImageSwitcher",
        "DipSwitch",
        "PushSwitch",
        "PushSwitchLed",
        "RockerSwitch",
        "PowerSwitch",
    ]:
        if candidate.lower() == normalized:
            return getattr(VisualElementType, candidate)
    raise Exception("Unsupported visualization element type '%s'." % name)


def _visual_event_type(name):
    normalized = str(name or "OnMouseClick").replace(" ", "").replace("-", "").replace("_", "").lower()
    for candidate in [
        "OnMouseClick",
        "OnMouseDown",
        "OnMouseUp",
        "OnMouseMove",
        "OnMouseEnter",
        "OnMouseLeave",
        "OnValueChanged",
        "OnDialogClosed",
    ]:
        if candidate.lower() == normalized:
            return getattr(InputActionEventType, candidate)
    raise Exception("Unsupported visualization input event '%s'." % name)


def _visual_properties(spec):
    properties = spec.get("properties", [])
    if isinstance(properties, dict):
        return [
            {
                "path": path,
                "value": value,
            }
            for path, value in properties.items()
        ]
    return list(properties)


def _create_visual_input_action(factory, spec):
    action_type = str(spec.get("type", "")).replace("-", "_").lower()
    if action_type in ["execute_st_code", "execute_st", "st"]:
        return factory.create_execute_st_code(str(spec["code"]))
    if action_type in ["write_variable", "write"]:
        return factory.create_write_variable(
            str(spec.get("variable", "")),
            str(spec.get("input_type", "Default")),
            str(spec.get("minimum", "")),
            str(spec.get("maximum", "")),
            str(spec.get("dialog_title", "")),
            bool(spec.get("password_input", False)),
            bool(spec.get("use_text_output_variable", False)),
        )
    if action_type in ["write_variable_default", "write_default"]:
        return factory.create_write_variable_default()
    raise Exception("Unsupported visualization input action type '%s'." % spec.get("type"))


def _upsert_visualization(request):
    project = _get_primary_project(request)
    container = _target_container(project, request)
    name = request["object_name"]
    visu = _find_child_by_name(container, name)
    created = False
    if visu is None:
        visu = container.create_visualobject(name)
        created = True

    element_list = visu.visual_element_list
    existing_elements = list(element_list)
    results = []
    errors = []
    visu.begin_modify()
    try:
        if request.get("replace_elements", True):
            for unused in existing_elements:
                element_list.remove_at(0)

        factory = visu.input_action_factory
        for index, spec in enumerate(request.get("elements", [])):
            element_result = {
                "index": index,
                "type": str(spec.get("type")),
                "properties": [],
                "actions": [],
            }
            element = element_list.add_element(_visual_element_type(spec.get("type")))
            element_result["id"] = int(element.id)

            for prop in _visual_properties(spec):
                prop_result = {
                    "path": str(prop.get("path")),
                    "value": _plain(prop.get("value")),
                }
                try:
                    element.set_property(str(prop["path"]), prop.get("value"))
                    try:
                        prop_result["read_back"] = _plain(element.get_property(str(prop["path"])))
                    except Exception:
                        pass
                    prop_result["ok"] = True
                except Exception as exc:
                    prop_result["ok"] = False
                    prop_result["error"] = str(exc)
                    errors.append({
                        "element_index": index,
                        "property": str(prop.get("path")),
                        "error": str(exc),
                    })
                element_result["properties"].append(prop_result)

            for action_spec in spec.get("actions", []):
                action_result = {
                    "event": str(action_spec.get("event", "OnMouseClick")),
                    "type": str(action_spec.get("type")),
                }
                try:
                    action = _create_visual_input_action(factory, action_spec)
                    element.add_input_action(
                        action,
                        _visual_event_type(action_spec.get("event", "OnMouseClick")),
                    )
                    action_result["ok"] = True
                except Exception as exc:
                    action_result["ok"] = False
                    action_result["error"] = str(exc)
                    errors.append({
                        "element_index": index,
                        "action": str(action_spec.get("type")),
                        "event": str(action_spec.get("event", "OnMouseClick")),
                        "error": str(exc),
                    })
                element_result["actions"].append(action_result)
            results.append(element_result)
    finally:
        visu.end_modify()

    if errors and request.get("strict", False):
        raise Exception(
            "Visualization '%s' contains %d configuration error(s): %s"
            % (name, len(errors), json.dumps(_plain(errors)))
        )

    saved = False
    if request.get("save", True):
        project.save()
        saved = True

    return {
        "project_path": _project_path(project),
        "container": _object_name(container),
        "visualization": _object_summary(visu, include_text=False),
        "created": created,
        "removed_element_count": len(existing_elements),
        "element_count": len(results),
        "elements": results,
        "errors": errors,
        "saved": saved,
    }


def _inspect_libraries(request):
    project = _get_primary_project(request)
    container = _target_container(project, request)
    libman = container.get_library_manager()
    queries = [
        str(item).lower()
        for item in request.get("queries", [])
        if str(item).strip()
    ]

    installed = []
    for library in librarymanager.get_all_libraries(not bool(request.get("all_versions", False))):
        record = {
            "repr": str(library),
            "type": str(type(library)),
            "attrs": {},
        }
        searchable = [record["repr"].lower()]
        for attr_name in [
            "name",
            "display_name",
            "localized_name",
            "version",
            "company",
            "default_namespace",
            "placeholder",
        ]:
            payload = _safe_attr_value(library, attr_name)
            record["attrs"][attr_name] = payload
            value = _attr_payload_value(payload)
            if value is not None:
                searchable.append(str(value).lower())
        haystack = " ".join(searchable)
        if not queries or any(query in haystack for query in queries):
            installed.append(record)

    def reference_record(reference):
        record = {
            "repr": str(reference),
            "type": str(type(reference)),
            "attrs": {},
        }
        for attr_name in [
            "id",
            "name",
            "namespace",
            "system_library",
            "is_placeholder",
            "is_managed",
            "placeholder_name",
            "default_resolution",
            "effective_resolution",
            "resolution_info",
        ]:
            record["attrs"][attr_name] = _safe_attr_value(reference, attr_name)
        return record

    references = []
    dependency_matches = []
    visited_references = set()

    def inspect_reference(reference, depth):
        record = reference_record(reference)
        name_value = _attr_payload_value(record["attrs"]["name"])
        key = str(name_value or record["repr"])
        if key in visited_references:
            return
        visited_references.add(key)

        haystack = " ".join([
            str(_attr_payload_value(payload) or "")
            for payload in record["attrs"].values()
        ]).lower()
        if not queries or any(query in haystack for query in queries):
            dependency_matches.append(record)

        if depth <= 0:
            return
        try:
            for dependency in reference.get_dependencies():
                inspect_reference(dependency, depth - 1)
        except Exception:
            pass

    try:
        for reference in libman.references:
            references.append(reference_record(reference))
            inspect_reference(reference, int(request.get("dependency_depth", 6)))
    except Exception:
        pass

    return {
        "project_path": _project_path(project),
        "container": _object_name(container),
        "library_manager": _object_name(libman),
        "libraries": _plain(list(libman.get_libraries(bool(request.get("recursive", False))))),
        "references": references,
        "dependency_matches": dependency_matches,
        "installed_matches": installed,
    }


def _ensure_library_placeholders(request):
    project = _get_primary_project(request)
    container = _target_container(project, request)
    libman = container.get_library_manager()
    existing = {}
    for reference in libman.references:
        placeholder_name = _get_plain_attr(reference, "placeholder_name")
        if placeholder_name:
            existing[str(placeholder_name)] = reference

    results = []
    for spec in request.get("placeholders", []):
        name = str(spec["name"])
        resolution = str(spec["resolution"])
        found = librarymanager.find_library(resolution)
        if found is None or len(found) < 1:
            raise Exception("Installed library '%s' was not found." % resolution)
        managed = found[0]

        if name in existing:
            reference = existing[name]
            before = _get_plain_attr(reference, "effective_resolution")
            reference.set_redirection(resolution)
            created = False
        else:
            libman.add_placeholder(name, managed)
            created = True
            reference = None
            for candidate in libman.references:
                if str(_get_plain_attr(candidate, "placeholder_name") or "") == name:
                    reference = candidate
                    break
            before = None

        if reference is not None:
            reference.set_redirection(resolution)

        results.append({
            "name": name,
            "resolution": resolution,
            "created": created,
            "effective_before": before,
            "effective_after": (
                _get_plain_attr(reference, "effective_resolution")
                if reference is not None
                else None
            ),
            "resolution_info": (
                _get_plain_attr(reference, "resolution_info")
                if reference is not None
                else None
            ),
        })

    fixed_results = []
    current_libraries = [str(item) for item in libman.get_libraries(False)]
    for resolution_value in request.get("libraries", []):
        resolution = str(resolution_value)
        found = librarymanager.find_library(resolution)
        if found is None or len(found) < 1:
            raise Exception("Installed library '%s' was not found." % resolution)
        created = resolution not in current_libraries
        if created:
            libman.add_library(found[0])
            current_libraries.append(resolution)
        fixed_results.append({
            "resolution": resolution,
            "created": created,
        })

    saved = False
    if request.get("save", True):
        project.save()
        saved = True

    return {
        "project_path": _project_path(project),
        "container": _object_name(container),
        "library_manager": _object_name(libman),
        "placeholders": results,
        "libraries": fixed_results,
        "saved": saved,
    }


def _remove_library_references(request):
    project = _get_primary_project(request)
    container = _target_container(project, request)
    libman = container.get_library_manager()
    existing = [str(item) for item in libman.get_libraries(False)]
    results = []
    for name_value in request.get("libraries", []):
        name = str(name_value)
        removed = name in existing
        if removed:
            libman.remove_library(name)
            existing.remove(name)
        results.append({
            "name": name,
            "removed": removed,
        })

    saved = False
    if request.get("save", True):
        project.save()
        saved = True
    return {
        "project_path": _project_path(project),
        "container": _object_name(container),
        "library_manager": _object_name(libman),
        "libraries": results,
        "saved": saved,
    }


def _configure_library_redirections(request):
    project = _get_primary_project(request)
    container = _target_container(project, request)
    libman = container.get_library_manager()
    requested = {
        str(spec["name"]): str(spec.get("resolution", ""))
        for spec in request.get("redirections", [])
    }
    found = {}
    visited = set()

    def visit(reference, depth):
        name = str(_get_plain_attr(reference, "name") or "")
        reference_id = str(_get_plain_attr(reference, "id") or name)
        key = name + "|" + reference_id
        if key in visited:
            return
        visited.add(key)

        placeholder_name = str(_get_plain_attr(reference, "placeholder_name") or "")
        if placeholder_name in requested and placeholder_name not in found:
            before = _get_plain_attr(reference, "effective_resolution")
            reference.set_redirection(requested[placeholder_name])
            found[placeholder_name] = {
                "name": placeholder_name,
                "requested_resolution": requested[placeholder_name],
                "effective_before": before,
                "effective_after": _get_plain_attr(reference, "effective_resolution"),
                "resolution_info": _get_plain_attr(reference, "resolution_info"),
            }

        if depth <= 0:
            return
        try:
            for dependency in reference.get_dependencies():
                visit(dependency, depth - 1)
        except Exception:
            pass

    for reference in libman.references:
        visit(reference, int(request.get("dependency_depth", 10)))

    missing = [name for name in requested if name not in found]
    if missing:
        raise Exception("Library placeholder(s) not found: %s" % ", ".join(missing))

    saved = False
    if request.get("save", True):
        project.save()
        saved = True
    return {
        "project_path": _project_path(project),
        "container": _object_name(container),
        "redirections": [found[name] for name in requested],
        "saved": saved,
    }


def _inspect_device_versions(request):
    project = _get_primary_project(request)
    name = request["object_name"]
    device = _find_descendant_by_name(project, name)
    if device is None:
        raise Exception("Device '%s' was not found." % name)
    current = device.get_device_identification()
    current_record = {
        "type": _get_plain_attr(current, "type"),
        "id": _get_plain_attr(current, "id"),
        "version": _get_plain_attr(current, "version"),
    }

    matches = []
    search_name = str(request.get("search_name", name.replace("_", " ")))
    for description in device_repository.get_all_devices(search_name, None):
        device_id = description.device_id
        info = description.device_info
        matches.append({
            "type": _get_plain_attr(device_id, "type"),
            "id": _get_plain_attr(device_id, "id"),
            "version": _get_plain_attr(device_id, "version"),
            "name": _get_plain_attr(info, "name"),
            "vendor": _get_plain_attr(info, "vendor"),
            "description": _get_plain_attr(info, "description"),
        })

    return {
        "project_path": _project_path(project),
        "device_name": _object_name(device),
        "current": current_record,
        "matches": matches,
    }


def _update_device_version(request):
    project = _get_primary_project(request)
    name = request["object_name"]
    device = _find_descendant_by_name(project, name)
    if device is None:
        raise Exception("Device '%s' was not found." % name)
    before = device.get_device_identification()
    before_record = {
        "type": _get_plain_attr(before, "type"),
        "id": _get_plain_attr(before, "id"),
        "version": _get_plain_attr(before, "version"),
    }

    requested_type = int(request.get("type", before_record["type"]))
    requested_id = str(request.get("id", before_record["id"]))
    requested_version = str(request["version"])
    requested_module = str(request.get("module", ""))
    device.update(
        requested_type,
        requested_id,
        requested_version,
        requested_module,
    )

    after = device.get_device_identification()
    after_record = {
        "type": _get_plain_attr(after, "type"),
        "id": _get_plain_attr(after, "id"),
        "version": _get_plain_attr(after, "version"),
    }
    saved = False
    if request.get("save", True):
        project.save()
        saved = True
    return {
        "project_path": _project_path(project),
        "device_name": _object_name(device),
        "before": before_record,
        "after": after_record,
        "saved": saved,
    }


def _upsert_function_block(request):
    project = _get_primary_project(request)
    container = _target_container(project, request)
    fb_name = request["fb_name"]
    declaration = request["declaration"].replace("\r\n", "\n").replace("\r", "\n").strip()
    implementation = request["implementation"].replace("\r\n", "\n").replace("\r", "\n").strip()

    fb, created_fb = _ensure_function_block(container, fb_name)

    changed_declaration = _declaration_text(fb).strip() != declaration
    if changed_declaration:
        _set_declaration_text(fb, declaration)

    changed_implementation = _implementation_text(fb).strip() != implementation
    if changed_implementation:
        _set_implementation_text(fb, implementation)

    saved = False
    if request.get("save", True) and (created_fb or changed_declaration or changed_implementation or project.dirty):
        project.save()
        saved = True

    return {
        "project_path": _project_path(project),
        "container": _object_name(container),
        "function_block": _object_name(fb),
        "created_function_block": created_fb,
        "changed_declaration": changed_declaration,
        "changed_implementation": changed_implementation,
        "saved": saved,
        "declaration": _declaration_text(fb),
        "implementation": _implementation_text(fb),
    }


def _rename_object(request):
    project = _get_primary_project(request)
    old_name = request["old_name"]
    new_name = request["new_name"]
    obj = _find_descendant_by_name(project, old_name)
    if obj is None:
        raise Exception("Object '%s' was not found." % old_name)
    obj.rename(new_name)

    saved = False
    if request.get("save", True):
        project.save()
        saved = True

    return {
        "project_path": _project_path(project),
        "old_name": old_name,
        "new_name": _object_name(obj),
        "saved": saved,
    }


def _set_device_enabled(request):
    project = _get_primary_project(request)
    device_name = request["device_name"]
    enabled = bool(request["enabled"])
    device = _find_descendant_by_name(project, device_name)
    if device is None:
        raise Exception("Device '%s' was not found." % device_name)
    if not getattr(device, "is_device", False):
        raise Exception("Object '%s' is not a device." % device_name)

    before = bool(device.is_enabled())
    if enabled and not before:
        device.enable()
    if not enabled and before:
        device.disable()
    after = bool(device.is_enabled())

    saved = False
    if request.get("save", True) and (before != after or project.dirty):
        project.save()
        saved = True

    return {
        "project_path": _project_path(project),
        "device_name": _object_name(device),
        "requested_enabled": enabled,
        "enabled_before": before,
        "enabled_after": after,
        "changed": before != after,
        "saved": saved,
    }


def _sync_device_enabled_from_uint_constant(request):
    project = _get_primary_project(request)
    constant_object_name = request.get("constant_object_name", "GVL")
    constant_name = request.get("constant_name", "uiUnits")
    device_name = request["device_name"]
    enable_when_at_least = int(request.get("enable_when_at_least", 2))

    constant_object = _find_descendant_by_name(project, constant_object_name)
    if constant_object is None:
        raise Exception("Constant object '%s' was not found." % constant_object_name)
    units = _extract_uint_constant(_declaration_text(constant_object), constant_name)
    enabled = units >= enable_when_at_least

    result = _set_device_enabled({
        "device_name": device_name,
        "enabled": enabled,
        "save": request.get("save", True),
    })
    result["constant_object_name"] = _object_name(constant_object)
    result["constant_name"] = constant_name
    result["constant_value"] = units
    result["enable_when_at_least"] = enable_when_at_least
    return result


def _collect_messages():
    collected = []
    try:
        categories = list(system.get_message_categories(True))
    except Exception:
        categories = []

    for category in categories:
        try:
            description = str(system.get_message_category_description(category))
        except Exception:
            description = str(category)
        try:
            messages = list(system.get_messages(category))
        except Exception:
            messages = []
        if messages:
            collected.append({
                "category": str(category),
                "description": description,
                "messages": [str(message) for message in messages],
            })
    return collected


def _clear_active_messages():
    try:
        categories = list(system.get_message_categories(True))
    except Exception:
        categories = []
    for category in categories:
        try:
            system.clear_messages(category)
        except Exception:
            pass


def _application_command(request):
    project = _get_primary_project(request)
    app = project.active_application
    if app is None:
        raise Exception("No active application is selected.")
    command = request.get("command", "build")
    if command not in ["build", "clean", "generate_code", "rebuild"]:
        raise Exception("Unsupported application command '%s'." % command)
    if request.get("clear_messages", True):
        _clear_active_messages()
    getattr(app, command)()
    system.delay(250)
    return {
        "project_path": _project_path(project),
        "active_application": _object_name(app),
        "command": command,
        "messages": _collect_messages(),
    }


def _build_properties_target(project, request):
    object_name = request.get("object_name")
    if object_name:
        target = _find_descendant_by_name(project, str(object_name))
    else:
        target = project.active_application
    if target is None:
        raise Exception("The build-properties target was not found.")

    build_properties = target.build_properties
    if build_properties is None:
        raise Exception(
            "Object '%s' has no editable build properties." % _object_name(target)
        )
    return target, build_properties


def _inspect_build_properties(request):
    project = _get_primary_project(request)
    target, build_properties = _build_properties_target(project, request)
    return {
        "project_path": _project_path(project),
        "object": _object_summary(target, include_text=False),
        "compiler_defines": _plain(build_properties.compiler_defines),
        "compiler_defines_is_valid": _plain(
            build_properties.compiler_defines_is_valid
        ),
    }


def _ensure_compiler_defines(request):
    project = _get_primary_project(request)
    target, build_properties = _build_properties_target(project, request)
    if not bool(build_properties.compiler_defines_is_valid):
        raise Exception(
            "Compiler defines are not valid for object '%s'."
            % _object_name(target)
        )

    before = str(build_properties.compiler_defines or "")
    entries = [item.strip() for item in before.split(",") if item.strip()]
    added = []
    for requested in request.get("defines", []):
        define = str(requested).strip()
        if define and define not in entries:
            entries.append(define)
            added.append(define)

    after = ", ".join(entries)
    if after != before:
        build_properties.compiler_defines = after

    saved = False
    if request.get("save", True):
        project.save()
        saved = True

    return {
        "project_path": _project_path(project),
        "object": _object_summary(target, include_text=False),
        "compiler_defines_before": before,
        "compiler_defines_after": str(build_properties.compiler_defines or ""),
        "added": added,
        "saved": saved,
    }


def _project_check_all_pool_objects(request):
    project = _get_primary_project(request)
    if request.get("clear_messages", True):
        _clear_active_messages()
    project.check_all_pool_objects()
    system.delay(int(request.get("delay_ms", 500)))
    messages = _collect_messages()

    lines = []
    message_count = 0
    for category in messages:
        lines.append(u"[%s] %s" % (
            _decode_text(category.get("category")),
            _decode_text(category.get("description")),
        ))
        for message in category.get("messages", []):
            lines.append(_decode_text(message))
            message_count += 1
    log_path = request.get("log_path")
    if log_path:
        _write_utf8(log_path, u"\n".join(lines))

    return {
        "project_path": _project_path(project),
        "message_categories": len(messages),
        "message_count": message_count,
        "log_path": log_path,
    }


def _online_application(request):
    project = _get_primary_project(request)
    app = project.active_application
    if app is None:
        raise Exception("No active application is selected.")
    return project, app


def _safe_online_attr(onlineapp, name):
    try:
        return _plain(getattr(onlineapp, name))
    except Exception as exc:
        return {"error": str(exc)}


def _online_snapshot(project, app, onlineapp):
    return {
        "project_path": _project_path(project),
        "active_application": _object_name(app),
        "is_logged_in": _safe_online_attr(onlineapp, "is_logged_in"),
        "application_state": _safe_online_attr(onlineapp, "application_state"),
        "operation_state": _safe_online_attr(onlineapp, "operation_state"),
        "is_online_change_possible": _safe_online_attr(
            onlineapp, "is_online_change_possible"
        ),
        "is_login_without_application": _safe_online_attr(
            onlineapp, "is_login_without_application"
        ),
    }


def _online_change_options():
    names = []
    try:
        for name in dir(OnlineChangeOption):
            if name.startswith("_"):
                continue
            try:
                value = getattr(OnlineChangeOption, name)
                if not _is_callable(value):
                    names.append(str(name))
            except Exception:
                pass
    except Exception:
        pass
    return sorted(names)


def _resolve_online_change_option(requested):
    requested = str(requested or "Try")
    normalized = requested.replace("_", "").replace("-", "").lower()
    for name in _online_change_options():
        candidate = name.replace("_", "").replace("-", "").lower()
        if candidate == normalized:
            return getattr(OnlineChangeOption, name), name
    raise Exception(
        "Unknown online change option '%s'. Available options: %s"
        % (requested, ", ".join(_online_change_options()))
    )


def _set_online_credentials(request):
    username = request.get("username")
    if username is None:
        return False
    password = request.get("password")
    online.set_default_credentials(str(username), password)
    return True


def _online_status(request):
    project, app = _online_application(request)
    with online.create_online_application(app) as onlineapp:
        data = _online_snapshot(project, app, onlineapp)
        data["change_options"] = _online_change_options()
        return data


def _online_login(request):
    project, app = _online_application(request)
    credentials_set = _set_online_credentials(request)
    option, option_name = _resolve_online_change_option(
        request.get("change_option", "Try")
    )
    with online.create_online_application(app) as onlineapp:
        if not bool(onlineapp.is_logged_in):
            onlineapp.login(option, bool(request.get("delete_foreign_apps", False)))
        system.delay(int(request.get("delay_ms", 1000)))
        if request.get("start", False):
            onlineapp.start()
            system.delay(int(request.get("start_delay_ms", 500)))
        data = _online_snapshot(project, app, onlineapp)
        data["change_option"] = option_name
        data["credentials_set"] = credentials_set
        return data


def _online_control(request):
    project, app = _online_application(request)
    command = str(request.get("command", "status")).lower()
    if command not in ["start", "stop", "logout"]:
        raise Exception("Unsupported online control command '%s'." % command)
    with online.create_online_application(app) as onlineapp:
        if command == "start":
            onlineapp.start()
        elif command == "stop":
            onlineapp.stop()
        else:
            onlineapp.logout()
        system.delay(int(request.get("delay_ms", 500)))
        return _online_snapshot(project, app, onlineapp)


def _online_read(request):
    project, app = _online_application(request)
    expressions = request.get("expressions", [])
    if not expressions:
        raise Exception("online_read requires a non-empty 'expressions' list.")
    expressions = [str(item) for item in expressions]
    with online.create_online_application(app) as onlineapp:
        if not bool(onlineapp.is_logged_in):
            raise Exception("The active application is not logged in.")
        system.delay(int(request.get("delay_ms", 500)))
        values = onlineapp.read_values(expressions)
        return {
            "status": _online_snapshot(project, app, onlineapp),
            "values": [
                {"expression": expression, "value": _plain(value)}
                for expression, value in zip(expressions, values)
            ],
        }


def _format_online_value(value):
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def _online_write(request):
    project, app = _online_application(request)
    values = request.get("values", [])
    if not values:
        raise Exception("online_write requires a non-empty 'values' list.")
    with online.create_online_application(app) as onlineapp:
        if not bool(onlineapp.is_logged_in):
            raise Exception("The active application is not logged in.")
        expressions = []
        for item in values:
            expression = str(item["expression"])
            expressions.append(expression)
            onlineapp.set_prepared_value(
                expression, _format_online_value(item["value"])
            )
        if request.get("force", False):
            onlineapp.force_prepared_values()
        else:
            onlineapp.write_prepared_values()
        system.delay(int(request.get("delay_ms", 500)))
        read_back = onlineapp.read_values(expressions)
        return {
            "status": _online_snapshot(project, app, onlineapp),
            "forced": bool(request.get("force", False)),
            "values": [
                {"expression": expression, "value": _plain(value)}
                for expression, value in zip(expressions, read_back)
            ],
        }


def handle_request(request):
    action = request.get("action")
    if action == "inspect":
        return {
            "ok": True,
            "action": action,
            "data": _inspect(request),
        }
    if action == "inspect_tree":
        return {
            "ok": True,
            "action": action,
            "data": _inspect_tree(request),
        }
    if action == "read_object":
        return {
            "ok": True,
            "action": action,
            "data": _read_object(request),
        }
    if action == "export_object_text_files":
        return {
            "ok": True,
            "action": action,
            "data": _export_object_text_files(request),
        }
    if action == "update_object_text_files":
        return {
            "ok": True,
            "action": action,
            "data": _update_object_text_files(request),
        }
    if action == "describe_object":
        return {
            "ok": True,
            "action": action,
            "data": _describe_object(request),
        }
    if action == "describe_device_details":
        return {
            "ok": True,
            "action": action,
            "data": _describe_device_details(request),
        }
    if action == "export_object_xml":
        return {
            "ok": True,
            "action": action,
            "data": _export_object_xml(request),
        }
    if action == "import_object_xml":
        return {
            "ok": True,
            "action": action,
            "data": _import_object_xml(request),
        }
    if action == "describe_script_symbol":
        return {
            "ok": True,
            "action": action,
            "data": _describe_script_symbol(request),
        }
    if action == "describe_device_parameters":
        return {
            "ok": True,
            "action": action,
            "data": _describe_device_parameters(request),
        }
    if action == "export_device_internal_config":
        return {
            "ok": True,
            "action": action,
            "data": _export_device_internal_config(request),
        }
    if action == "import_device_internal_config":
        return {
            "ok": True,
            "action": action,
            "data": _import_device_internal_config(request),
        }
    if action == "describe_device_driver_info":
        return {
            "ok": True,
            "action": action,
            "data": _describe_device_driver_info(request),
        }
    if action == "set_device_parameter_value":
        return {
            "ok": True,
            "action": action,
            "data": _set_device_parameter_value(request),
        }
    if action == "set_device_diagnosis_enabled":
        return {
            "ok": True,
            "action": action,
            "data": _set_device_diagnosis_enabled(request),
        }
    if action == "delete_objects":
        return {
            "ok": True,
            "action": action,
            "data": _delete_objects(request),
        }
    if action == "add_gvl_var":
        return {
            "ok": True,
            "action": action,
            "data": _add_gvl_var(request),
        }
    if action == "upsert_object":
        return {
            "ok": True,
            "action": action,
            "data": _upsert_object(request),
        }
    if action == "upsert_visualization":
        return {
            "ok": True,
            "action": action,
            "data": _upsert_visualization(request),
        }
    if action == "inspect_libraries":
        return {
            "ok": True,
            "action": action,
            "data": _inspect_libraries(request),
        }
    if action == "ensure_library_placeholders":
        return {
            "ok": True,
            "action": action,
            "data": _ensure_library_placeholders(request),
        }
    if action == "remove_library_references":
        return {
            "ok": True,
            "action": action,
            "data": _remove_library_references(request),
        }
    if action == "configure_library_redirections":
        return {
            "ok": True,
            "action": action,
            "data": _configure_library_redirections(request),
        }
    if action == "inspect_device_versions":
        return {
            "ok": True,
            "action": action,
            "data": _inspect_device_versions(request),
        }
    if action == "update_device_version":
        return {
            "ok": True,
            "action": action,
            "data": _update_device_version(request),
        }
    if action == "upsert_function_block":
        return {
            "ok": True,
            "action": action,
            "data": _upsert_function_block(request),
        }
    if action == "rename_object":
        return {
            "ok": True,
            "action": action,
            "data": _rename_object(request),
        }
    if action == "set_device_enabled":
        return {
            "ok": True,
            "action": action,
            "data": _set_device_enabled(request),
        }
    if action == "sync_device_enabled_from_uint_constant":
        return {
            "ok": True,
            "action": action,
            "data": _sync_device_enabled_from_uint_constant(request),
        }
    if action == "application_command":
        return {
            "ok": True,
            "action": action,
            "data": _application_command(request),
        }
    if action == "inspect_build_properties":
        return {
            "ok": True,
            "action": action,
            "data": _inspect_build_properties(request),
        }
    if action == "ensure_compiler_defines":
        return {
            "ok": True,
            "action": action,
            "data": _ensure_compiler_defines(request),
        }
    if action == "project_check_all_pool_objects":
        return {
            "ok": True,
            "action": action,
            "data": _project_check_all_pool_objects(request),
        }
    if action == "online_status":
        return {
            "ok": True,
            "action": action,
            "data": _online_status(request),
        }
    if action == "online_login":
        return {
            "ok": True,
            "action": action,
            "data": _online_login(request),
        }
    if action == "online_control":
        return {
            "ok": True,
            "action": action,
            "data": _online_control(request),
        }
    if action == "online_read":
        return {
            "ok": True,
            "action": action,
            "data": _online_read(request),
        }
    if action == "online_write":
        return {
            "ok": True,
            "action": action,
            "data": _online_write(request),
        }
    raise Exception("Unsupported action '%s'." % action)


def main():
    request = _load_request()
    result_path = request.get("result_path")

    try:
        _write_result(result_path, handle_request(request))
    except Exception as exc:
        _write_result(result_path, {
            "ok": False,
            "action": request.get("action"),
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })
        raise


if __name__ == "__main__":
    main()
