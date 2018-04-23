'''
Put this file in ~/.vim/python3 and add this to your vimrc:

au FileType python py3 from jedi_extract_variable import extract_variable
au FileType python noremap <buffer> <F4> :py3 extract_variable()<CR>
au FileType python inoremap <buffer> <F4> <C-\><C-O>:py3 extract_variable()<CR>

Change <F4> to whatever key you want.
'''
import vim
import jedi
import collections
import parso.python.tree
from jedi_vim import echo_highlight, get_script, _check_jedi_availability, catch_and_print_exceptions


def capture_inserted_text(fn):
    @_check_jedi_availability(show_error=True)
    @catch_and_print_exceptions
    def wrapper():
        continuation._changenr = vim.eval('changenr()')
        continuation._saved_view = vim.eval('string(winsaveview())')
        continuation._fn = fn()
        data = continuation._fn.send(None)
        # echo_highlight('coro returned ' + str(data))
        if data is None:
            vim.command('augroup jedistuff_continuation')
            vim.command('au!')
            vim.command('autocmd InsertLeave <buffer> py3 jedistuff.continuation()')
            vim.command('augroup END')
            vim.command('startinsert')

    return wrapper


Continuation = collections.namedtuple('Continuation', 'text undo')


def continuation():
    vim.command('augroup jedistuff_continuation')
    vim.command('au!')
    vim.command('augroup END')
    fn = continuation._fn
    del continuation._fn  # Ensure AttributeError if called out of line

    def undo():
        vim.command('undo {}'.format(continuation._changenr))
        vim.command('call winrestview(%s)' % continuation._saved_view)

    cont = Continuation(vim.eval('@.'), undo)
    # echo_highlight('sending into coro ' + str(cont))
    try:
        fn.send(cont)
    except StopIteration:
        pass
    else:
        echo_highlight('Expected generator to stop')


def leaf_is_getattr(node):
    return (node.parent.type == 'trailer' and
            node.parent.children[0] == '.')


def enclosing_statement(node):
    while node.parent and not node.type.endswith('_stmt'):
        node = node.parent
    return node


def leaf_is_brace(leaf):
    return (leaf == '(' or leaf == '[' or leaf == '{' or
            leaf == '}' or leaf == ']' or leaf == ')')


@capture_inserted_text
def extract_variable():
    script: jedi.Script = get_script()
    module: parso.python.tree.Module = script._module_node
    position = script._pos
    leaf = module.get_leaf_for_position(position, include_prefixes=True)
    if leaf_is_getattr(leaf) or (leaf_is_brace(leaf) and leaf.parent.type == 'trailer'):
        trailer = leaf.parent
        assert trailer.type == 'trailer'
        atom = trailer.parent
        assert atom.type in 'atom atom_expr'.split(), atom.type
        start_pos = atom.start_pos
        end_pos = trailer.end_pos
    elif leaf_is_brace(leaf):
        node = leaf.parent
        if node.type in 'decorator parameters import_from classdef'.split():
            return (yield 1)
        assert leaf_is_brace(node.children[0]) and leaf_is_brace(node.children[-1])
        start_pos = node.start_pos
        end_pos = node.end_pos
    else:
        start_pos = leaf.start_pos
        end_pos = leaf.end_pos

    virtualedit = vim.eval('&virtualedit')
    vim.command('set virtualedit=onemore')
    cmd = ('norm! %sG%s|mt%sG%s|"rd`t' %
           (end_pos[0], end_pos[1]+1, start_pos[0], start_pos[1]+1))
    # echo_highlight('sending command ' + cmd)
    vim.command(cmd)
    text = vim.eval('@"')
    stmt = enclosing_statement(leaf)
    inserted = yield
    # echo_highlight('inserted is ' + str(inserted))
    if not inserted.text:
        vim.command('set virtualedit=%s' % virtualedit)
        return inserted.undo()
    vim.current.window.cursor = stmt.start_pos
    vim.command('norm! O%s = ' % inserted.text)
    vim.command('norm! "rp')
    vim.command('set virtualedit=%s' % virtualedit)
