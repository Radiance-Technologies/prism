/*
 * Copyright (c) 2023 Radiance Technologies, Inc.
 *
 * This file is part of PRISM
 * (see https://github.com/orgs/Radiance-Technologies/prism).
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Lesser General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this program. If not, see
 * <http://www.gnu.org/licenses/>.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <codecvt>
#include <locale>
#include <sstream>
#include <vector>

// #define EMBEDDED
#ifdef EMBEDDED
int pyinit()
{
    /* WARNING: this does not work. Modules fail to import. */
    std::wstringstream path;
    path << "/path/to/your/python/bin:";
    path << "/path/to/your/coq-pearls:";
    path << Py_GetPath();
    Py_SetPath(path.str().c_str());
    Py_Initialize();
    return 0;
}

const int init = pyinit();
#endif


/* import constructors */
PyObject*     sexp_list_mod   = PyImport_ImportModule("prism.language.sexp.list");
PyObject*     sexp_string_mod = PyImport_ImportModule("prism.language.sexp.string");
PyObject*     SexpList        = PyObject_GetAttrString(sexp_list_mod, "SexpList");
PyObject*     SexpString      = PyObject_GetAttrString(sexp_string_mod, "SexpString");
const Py_UCS4 c_quote         = '"';
const Py_UCS4 c_escape        = '\\';
const Py_UCS4 c_lpar          = '(';
const Py_UCS4 c_rpar          = ')';

#ifdef Py_LIMITED_API
/**********************************************************************/
/* Copied code since it isn't clear that it is part of the stable ABI */
/**********************************************************************/

// Helper array used by Py_UNICODE_ISSPACE().
/* Fast detection of the most frequent whitespace characters */
const unsigned char __Py_ascii_whitespace[] = {
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    /*     case 0x0009: * CHARACTER TABULATION */
    /*     case 0x000A: * LINE FEED */
    /*     case 0x000B: * LINE TABULATION */
    /*     case 0x000C: * FORM FEED */
    /*     case 0x000D: * CARRIAGE RETURN */
    0,
    1,
    1,
    1,
    1,
    1,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    /*     case 0x001C: * FILE SEPARATOR */
    /*     case 0x001D: * GROUP SEPARATOR */
    /*     case 0x001E: * RECORD SEPARATOR */
    /*     case 0x001F: * UNIT SEPARATOR */
    0,
    0,
    0,
    0,
    1,
    1,
    1,
    1,
    /*     case 0x0020: * SPACE */
    1,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,

    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0};

/* Returns 1 for Unicode characters having the bidirectional
 * type 'WS', 'B' or 'S' or the category 'Zs', 0 otherwise.
 *
 * Copied from https://github.com/python/cpython/blob/main/Objects/unicodetype_db.h.
 */
inline int _PyUnicode_IsWhitespace(const Py_UCS4 ch)
{
    switch (ch)
    {
        case 0x0009:
        case 0x000A:
        case 0x000B:
        case 0x000C:
        case 0x000D:
        case 0x001C:
        case 0x001D:
        case 0x001E:
        case 0x001F:
        case 0x0020:
        case 0x0085:
        case 0x00A0:
        case 0x1680:
        case 0x2000:
        case 0x2001:
        case 0x2002:
        case 0x2003:
        case 0x2004:
        case 0x2005:
        case 0x2006:
        case 0x2007:
        case 0x2008:
        case 0x2009:
        case 0x200A:
        case 0x2028:
        case 0x2029:
        case 0x202F:
        case 0x205F:
        case 0x3000:
            return 1;
    }
    return 0;
};

// Since splitting on whitespace is an important use case, and
// whitespace in most situations is solely ASCII whitespace, we
// optimize for the common case by using a quick look-up table
// _Py_ascii_whitespace (see below) with an inlined check.
#define Py_UNICODE_ISSPACE(ch) \
    ((ch) < 128U ? __Py_ascii_whitespace[(ch)] : _PyUnicode_IsWhitespace(ch))

/**********************************************************************/
/*                            End copied code                         */
/**********************************************************************/
#endif


std::string wstring_to_string(const std::wstring& wstr)
{
    static std::wstring_convert<std::codecvt_utf8<wchar_t>, wchar_t> converter;
    return converter.to_bytes(wstr);
}

std::wstring string_to_wstring(const std::string& str)
{
    static std::wstring_convert<std::codecvt_utf8<wchar_t>, wchar_t> converter;
    return converter.from_bytes(str);
}

PyObject* sexp_parse(PyObject* sexp_str)
{
    std::vector<PyObject*> return_stack;
    return_stack.push_back(PyList_New(0));
    Py_ssize_t str_len = PyUnicode_GetLength(sexp_str);
#ifndef Py_LIMITED_API
    unsigned int kind         = PyUnicode_KIND(sexp_str);
    void*        unicode_data = PyUnicode_DATA(sexp_str);
#endif
    std::wstring quoted   = L"";
    bool         escaped  = false;
    std::wstring terminal = L"";

    for (int i = 0; i < str_len; i++)
    {
#ifdef Py_LIMITED_API
        Py_UCS4 cur_char = PyUnicode_ReadChar(sexp_str, i);
#else
        Py_UCS4 cur_char = PyUnicode_READ(kind, unicode_data, i);
#endif
        if (!terminal.empty())
        {
            if (!quoted.empty())
            {
                /* Release accumulated SexpNodes */
                for (const auto& py_object: return_stack)
                {
                    Py_DecRef(py_object);
                }
                PyErr_SetString(PyExc_AssertionError, "quoted is not empty");
                return NULL;
            }
            else if (escaped)
            {
                // Escape the character
                switch ((wchar_t)cur_char)
                {
                    case '\\':
                        // cur_char stays the same
                        break;
                    case '\'':
                        // cur_char stays the same
                        break;
                    case '\"':
                        // cur_char stays the same
                        break;
                    case 'b':
                        cur_char = (Py_UCS4)'\b';
                        break;
                    case 'f':
                        cur_char = (Py_UCS4)'\014';
                        break;
                    case 't':
                        cur_char = (Py_UCS4)'\t';
                        break;
                    case 'n':
                        cur_char = (Py_UCS4)'\n';
                        break;
                    case 'r':
                        cur_char = (Py_UCS4)'\r';
                        break;
                    case 'v':
                        cur_char = (Py_UCS4)'\013';
                        break;
                    case 'a':
                        cur_char = (Py_UCS4)'\007';
                        break;
                    default:
                        terminal.push_back('\\');
                        break;
                }
            }
            if (!escaped and (cur_char == c_lpar or cur_char == c_rpar or
                              cur_char == c_quote or Py_UNICODE_ISSPACE(cur_char)))
            {
                // conclude terminal
                PyObject* new_char =
                    PyUnicode_FromWideChar(terminal.c_str(), terminal.length());
                PyObject* sexp_string =
                    PyObject_CallFunctionObjArgs(SexpString, new_char, NULL);
                Py_DecRef(new_char);
                PyList_Append(return_stack.back(), sexp_string);
                Py_DecRef(sexp_string);
                terminal = L"";
            }
            else
            {
                escaped = false;
                terminal.push_back((wchar_t)cur_char);
                continue;
            }
        }
        if (escaped)
        {
            // escape the character
            switch ((wchar_t)cur_char)
            {
                case '\\':
                    // cur_char stays the same
                    break;
                case '\'':
                    // cur_char stays the same
                    break;
                case '\"':
                    // cur_char stays the same
                    if (!quoted.empty())
                    {
                        // keep double-quotes escaped if inside of a quote
                        quoted.push_back('\\');
                    }
                    break;
                case 'b':
                    cur_char = (Py_UCS4)'\b';
                    break;
                case 'f':
                    cur_char = (Py_UCS4)'\014';
                    break;
                case 't':
                    cur_char = (Py_UCS4)'\t';
                    break;
                case 'n':
                    cur_char = (Py_UCS4)'\n';
                    break;
                case 'r':
                    cur_char = (Py_UCS4)'\r';
                    break;
                case 'v':
                    cur_char = (Py_UCS4)'\013';
                    break;
                case 'a':
                    cur_char = (Py_UCS4)'\007';
                    break;
                default:
                    if (!quoted.empty())
                    {
                        quoted.push_back('\\');
                    }
                    else
                    {
                        terminal.push_back('\\');
                    }
                    break;
            }
        }
        else if (cur_char == c_escape)
        {
            // Escape the next character
            escaped = true;
            continue;
        }
        if (!quoted.empty())
        {
            // extend or conclude string literal
            if (!escaped and cur_char == c_quote)
            {
                // End string literal
                // Consume the ending quote
                quoted.push_back('"');
                PyObject* new_char =
                    PyUnicode_FromWideChar(quoted.c_str(), quoted.length());
                PyObject* sexp_string =
                    PyObject_CallFunctionObjArgs(SexpString, new_char, NULL);
                Py_DecRef(new_char);
                PyList_Append(return_stack.back(), sexp_string);
                Py_DecRef(sexp_string);
                quoted = L"";
            }
            else
            {
                escaped = false;
                quoted.push_back((wchar_t)cur_char);
            }
        }
        else if (!escaped)
        {
            if (Py_UNICODE_ISSPACE(cur_char))
            {
                // consume whitespace
                continue;
            }
            else if (cur_char == c_lpar)
            {
                // consume the left paren
                // Start SexpList
                return_stack.push_back(PyList_New(0));
            }
            else if (cur_char == c_rpar)
            {
                // Consume the right paren
                // End SexpList
                PyObject* children = return_stack.back();
                return_stack.pop_back();
                if (return_stack.empty())
                {
                    // too many close parens
                    wchar_t*     copy  = PyUnicode_AsWideCharString(sexp_str, &str_len);
                    std::wstring wcopy = copy;
                    PyMem_Free(copy);
                    std::stringstream error_msg;
                    error_msg << "Extra close parenthesis at index " << i;
                    error_msg << " of " << wstring_to_string(wcopy);
                    PyErr_SetString(PyExc_ValueError, error_msg.str().c_str());
                    /* Release accumulated SexpNodes */
                    Py_DecRef(children);
                    return NULL;
                }
                PyObject* sexp_list =
                    PyObject_CallFunctionObjArgs(SexpList, children, NULL);
                Py_DecRef(children);
                PyList_Append(return_stack.back(), sexp_list);
                Py_DecRef(sexp_list);
            }
            else if (cur_char == c_quote)
            {
                // Start string literal
                quoted = L"\"";
            }
            else
            {
                // Start a normal token
                escaped = false;
                terminal.push_back((wchar_t)cur_char);
            }
        }
        else
        {
            // Start a normal token (with an escaped first character)
            escaped = false;
            terminal.push_back((wchar_t)cur_char);
        }
    }
    if (!terminal.empty())
    {
        // conclude terminal
        PyObject* new_char =
            PyUnicode_FromWideChar(terminal.c_str(), terminal.length());
        PyObject* sexp_string =
            PyObject_CallFunctionObjArgs(SexpString, new_char, NULL);
        Py_DecRef(new_char);
        PyList_Append(return_stack.back(), sexp_string);
        Py_DecRef(sexp_string);
    }
    if (return_stack.size() != 1 or PyList_Size(return_stack.front()) == 0)
    {
        bool do_abbreviate = str_len > 100;
        if (do_abbreviate)
        {
            sexp_str = PyUnicode_Substring(sexp_str, 0, 72);
        }
        PyObject* msg_start = PyUnicode_FromString("Malformed sexp: ");
        PyObject* msg       = PyUnicode_Concat(msg_start, sexp_str);
        if (do_abbreviate)
        {
            Py_DecRef(sexp_str);
        }
        Py_DecRef(msg_start);
        PyObject* exc = PyObject_CallFunctionObjArgs(PyExc_ValueError, msg, NULL);
        Py_DecRef(msg);
        PyErr_SetObject(PyExc_ValueError, exc);
        Py_DecRef(exc);
        /* Release accumulated SexpNodes */
        for (const auto& py_object: return_stack)
        {
            Py_DecRef(py_object);
        }
        return NULL;
    }
    return return_stack.front();
};

static PyObject* py_sexp_parse(PyObject* self, PyObject* args)
{
    PyObject* sexp_str = NULL;
    if (!PyArg_ParseTuple(args, "U", &sexp_str))
    {
        return NULL;
    }
    PyObject* sexps = sexp_parse(sexp_str);
    return sexps;
};

static PyMethodDef ParsingMethods[] = {
    {"parse_sexps",
     py_sexp_parse,       METH_VARARGS,
     "Parse a string of a list of s-expressions into `SexpNode`s."},
    {NULL,          NULL, 0,            NULL                      }
};

static struct PyModuleDef sexp_parse_module = {PyModuleDef_HEAD_INIT,
                                               "prism.language.sexp._parse",
                                               "Library for parsing s-expressions",
                                               -1,
                                               ParsingMethods};

PyMODINIT_FUNC            PyInit__parse(void)
{
    return PyModule_Create(&sexp_parse_module);
};


#ifdef EMBEDDED
int main(int arc, char** argv)
{
    /* Simple standalone test for debugging. */
    PyObject* sexp_str      = PyUnicode_FromString("");
    PyObject* list_of_sexps = sexp_parse(sexp_str);
    int       size          = (int)PyList_Size(list_of_sexps);
    Py_Finalize();
    return size;
}
#endif
