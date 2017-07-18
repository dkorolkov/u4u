function WebApp(socket) {
    var addUser = function addUser(event) {
        var params;
        event.preventDefault();
        params = {};
        $('#add_user_form').serializeArray().forEach(function(item) {
            params[item.name] = item.value;
        });
        if (params['id']) {
            params['command'] = 'update_user';
        } else {
            params['command']= 'add_user';
            delete params['id'];
        }
        socket.send(JSON.stringify(params));
        clearForm();
    };

    var editUser = function editUser(user_data) {
        var form;
        form = $('#add_user_form');
        Object.keys(user_data).forEach((key) => {form.find('[name=' + key + ']').val(user_data[key])});
        form.removeClass('add').addClass('edit');
    };

    var deleteUser = function deleteUser(user_id) {
        socket.send(JSON.stringify({command: 'delete_user', id: user_id}));
    };

    var clearForm = function clearForm(event) {
        if (event) {
            event.preventDefault();
        }
        $('#add_user_form input[type=text]').val('');
        $('#add_user_form input[type=hidden]').val('');
        $('#add_user_form').removeClass('edit').addClass('add');
    };

    var insertRow = function insertRow(user_data) {
        var table, tr,
            td_first_name, td_last_name, td_email, td_password,
            td_edit, td_delete, edit_button, delete_button;

        table = $('#user_table');
        tr = $('<tr>').attr('id', 'user_' + user_data.id);
        td_first_name = $('<td>').addClass('first_name').html(user_data.first_name);
        td_last_name = $('<td>').addClass('last_name').html(user_data.last_name);
        td_email = $('<td>').addClass('email').html(user_data.email);
        td_password = $('<td>').addClass('password').html(user_data.password);
        edit_button = $('<button>').addClass('edit_button').html('Редактировать').click(editUser.bind(null, user_data));
        td_edit = $('<td>');
        td_edit.append(edit_button);
        delete_button = $('<button>').html('Удалить').click(deleteUser.bind(null, user_data.id));
        td_delete = $('<td>');
        td_delete.append(delete_button);
        tr.append(td_first_name);
        tr.append(td_last_name);
        tr.append(td_email);
        tr.append(td_password);
        tr.append(td_edit);
        tr.append(td_delete);
        table.append(tr);
    };

    var showUserList = function showUserList(data) {
        var i;

        for (i=0; i<data.length; ++i) {
            insertRow(data[i]); 
        }
    };

    var addUserResponce = function addUserResponce(data) {
        insertRow(data); 
    };

    var updateUserResponce = function updateUserResponce(data) {
        var user_id, tr;

        user_id = data['id'];
        delete data['id'];
        tr = $('#user_' + user_id);
        Object.keys(data).forEach((key) => {tr.children('.' + key).html(data[key])});
        tr.find('.edit_button').click(editUser.bind(null, data));
    };

    var deleteUserResponce = function deleteUserResponce(data) {
        var user_id, tr;

        user_id = data['id'];
        $('#user_' + user_id).remove();
    };

    var commands = {
        get_user_list: showUserList,
        add_user: addUserResponce,
        update_user: updateUserResponce,
        delete_user: deleteUserResponce
    };

    var commandExecute = function commandExecute(command, data) {
        var handler;
        handler = commands[command];
        if (handler) {
            handler(data);
        }
    };

    return {
        addUser: addUser,
        deleteUser: deleteUser,
        commandExecute: commandExecute,
        clearForm: clearForm
    };
}

var webApp;

$(document).ready(function() {
    var socket = new WebSocket("ws://localhost:8000/ws");

    webApp = WebApp(socket);

    socket.onopen = function() {
      socket.send(JSON.stringify({command: 'get_user_list'}));
    };

    socket.onmessage = function(message_event) {
        var data, ok, command;
        data = JSON.parse(message_event.data);
        ok = data.ok;
        if (ok) {
            command = ok.command;
            if (command) {
                webApp.commandExecute(command, ok.result);
            }
        }
    };

    socket.onclose = function() {
    };

    $('#add_user_form').submit(webApp.addUser);
    $('#clear_form').click(webApp.clearForm);

});
