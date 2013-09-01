var hash=''
jQuery.support.cors = true;

$(document).ready(function(){
var current_title = $(document).attr('title');
var path = window.location.pathname;
var pagename = path.match(/.*\/([^/]+)\.([^?]+)/i)[1];
$('#pagename').html(pagename);
if ((pagename == 'feeds') || (pagename == 'monitor'))
	{
	$.getJSON('/'+pagename, populate_files);
    }

if (pagename == 'config')
	{
	$.getJSON('/ajax/config', populate);
	$(function(){
  	$('legend').click(function(){
            $(this).siblings().toggle();
            });
});
	}
if (pagename == 'favorites')
	{
	$.getJSON('/ajax/favorites', populate_nested);
    }
build_buttons();

function set(data)
{
$.each(data, function(name, value) {
 window[name]=value;
});
    if (ajax_debug)
    {
    $(".debug").toggle();
    }
    s_update_id = setInterval(s_update, ajax_refresh);
    g_update_id = setInterval(g_update, ajax_refresh*3);
    vs_update_id = setInterval(vs_update, ajax_refresh*4);
}

function globals(data)
{
//console.log(data);
$.each(data, function(name, value) {
            $("#"+name).html(value);
            if ((name=='g_att' && value=='1') || (name=='g_mute' && value=='1') || (name=='g_record' && value=='1'))
                    {
                        $(".ind_"+name).css("color",'red');
                    }
            else
                    {
                        $(".ind_"+name).css("color",'lightgrey');
                    }
});
}
function populate_nested(data)
{
$.each(data, function(name, value) {            
            for (var prop in value) {
            element="#"+prop+"_"+name          
            $(element).parent().show();
            tagname=$(element).prop("tagName")
            type=$(element).attr('type')
            $(element).prop('title', value[prop]);
            if (tagname=="SELECT")
            {
            $(element).children('option').each(function() {
                if ($(this).val()==value[prop]) $(this).attr("selected",true)
            });
            }
            else if (tagname=="INPUT")
            {
            if (type='checkbox')
            {
            if ($(element).val()==value[prop]) $(element).attr("checked",true)
            } else $(element).prop('value', value[prop]); 
            }
            else
            {
            $(element).html(value[prop]);
            }  
}        
});
}    

function populate_files(data)
{
$('#file_content').empty();
$.each(data, function(name, value) {
$('#file_content').append("<div class='w20 left'><a href='/"+pagename+"/"+value+"'>"+value+"</a></div>");
});
}

function populate(data)
{
if (hash!=data.hash)
{
// console.log(data);
hash=data.hash;
$.each(data, function(name, value) {
            element="#"+name
            tagname=$(element).prop("tagName")
            type=$(element).attr('type')
            $(element).prop('title', value);
            if (name=="hp_mode")
            {
                $("#VOL-"+value).html($("#VOL").html())
                if ($("#"+value).css("display") == "none")
                    {
                    $('.menubar').hide();
                    $("#"+value).show();
                    }
            }
            if (tagname=="SELECT")
            {
            $(element).children('option').each(function() {
                if ($(this).val()==value) $(this).attr("selected",true)
            });
            }
            else if (tagname=="INPUT")
            {
            $("#"+name).prop('value', value);
            }
            else
            {
            $(element).html(value);
            }          
            if (name=="channel")
            {
            if (value==null)
            {
            $(document).attr('title', current_title);
            }
            else
            {
            $(document).attr('title', value);
            }
            }
            if ((name=="channel_avoid") || (name=="department_avoid") || (name=="system_avoid") || (name=="channel_hold") || (name=="department_hold") || (name=="system_hold"))
                {
                if (value=="1") 
                    {
                        color="CornflowerBlue";
                    }
                else 
                    {
                        color="silver";
                    }
                $("#ind_"+name).css("background-color",color);
                }
            
            if (name=="signal")
                {
                siglevel=parseInt(value)
                for (i=0; i<5; i++)
                {
                if (i<=siglevel) 
                    {
                        color="limegreen"; 
                    }
                else 
                    {
                        color="silver";
                    }
                $(".sbar-"+i.toString()).css("background-color",color);
                }
                }
            if ( value == null )
                {
                    $("#"+name).addClass('empty');
                }
            else
                { 
                    $("#"+name).removeClass('empty');
                }
});
}    
}
function s_update() {
$.getJSON('ajax/monitor', populate);
}
function g_update() {
$.getJSON('ajax/globals', globals);
}

function vs_update() {
$.getJSON('ajax/volsql', populate);
}

function c_update() {
$.getJSON('ajax/config', populate);
}

function status_candy(){
}

function kill_button(){
var r=confirm("WARNING!\n\nIt is not possible to restart HPe-rc from the web interface.\nPress OK to terminate the program on the host machine.");
    if (r==true)
    {
    $.get("/kill");
    }
}

function build_buttons() {
    $('#mute-button').on('click', function(){
        $.get("/toggle/mute");
        setTimeout(g_update, 600);
        });
    $('#att-button').on('click', function(){
        $.get("/toggle/gatt");
        setTimeout(g_update, 600);
        });
    $('#record-button').on('click', function(){
        $.get("/toggle/record");
        setTimeout(g_update, 600);
        });
   $('#screenshot-button').on('click', function(){
        $.get("/command/cap");
        });
    $('#ind_channel_hold, #touch_channel_hold').on('click', function(){
        $.get("/toggle/chold");
        });
    $('#ind_department_hold, #touch_department_hold').on('click', function(){
        $.get("/toggle/dhold");
        });        
    $('#ind_system_hold, #touch_system_hold').on('click', function(){
        $.get("/toggle/shold");
        });        
   $('#ind_channel_avoid').on('click', function(){
        $.get("/toggle/cavoid");
        });
    $('#ind_department_avoid').on('click', function(){
        $.get("/toggle/davoid");
        });        
    $('#ind_system_avoid').on('click', function(){
        $.get("/toggle/savoid");
        });                
        
   $('#ind_channel_next, #touch_channel_next').on('click', function(){
        $.get("/command/cnext");
        });
    $('#ind_department_next, #touch_department_next').on('click', function(){
        $.get("/command/dnext");
        });        
    $('#ind_system_next, #touch_system_next').on('click', function(){
        $.get("/command/snext");
        });                      

    $('#ind_channel_prev, #touch_channel_prev').on('click', function(){
        $.get("/command/cprev");
        });
    $('#ind_department_prev, #touch_department_prev').on('click', function(){
        $.get("/command/dprev");
        });        
    $('#ind_system_prev, #touch_system_prev').on('click', function(){
        $.get("/command/sprev");
        });                      
   $('[id^=scan-button]').on('click', function(){
        $.get("/command/scan");
        });
   $('[id^=kill-button]').on('click', kill_button);
   
   $('#replay-button').on('click', function(){
        $.get("/command/replay");
        });
   $('#rp_next').on('click', function(){
        $.get("/rep/next");
        });        
   $('#rp_prev').on('click', function(){
        $.get("/rep/prev");
        });        
   $('#rp_pause').on('click', function(){
        $('#rp_pause').toggleClass('pause')
        if ($('#rp_pause').hasClass('pause'))
        {
        $('#rp_pause .text').html('PAUSE');
        $.get("/rep/resume");
        }
        else
        {
        $('#rp_pause .text').html('RESUME');
        $.get("/rep/pause");
        }
        });  
   $('[id^=vol_up]').on('click', function(){
        $.get("/+/vol");
        setTimeout(vs_update, 600);
        });
    $('[id^=vol_down]').on('click', function(){
        $.get("/-/vol");
        setTimeout(vs_update, 600);
        });
    $('#sql_up').on('click', function(){
        $.get("/+/sql");
        setTimeout(vs_update, 600);
        });
    $('#sql_down').on('click', function(){
        $.get("/-/sql");
        setTimeout(vs_update, 600);
        });        
        }   
    $('#test-data').on('click', function(){
        $.getJSON('/ajax/test', populate); 
        });
    $('#tool_button').on('click', function(){
        $('#tool_menu').fadeToggle("fast");
        });                

    $('#tool_menu').on('click', function(){
        $('#tool_menu').fadeToggle("fast");
        });  

    $('#config-current').on('click', function(){
        $.getJSON('/ajax/config', populate);
        });
        
    $('#config-default').on('click', function(){
        $.getJSON('/ajax/defaults', populate);
        });
    
    $('#stop-button').on('click', function(){
        clearInterval(s_update_id);
        clearInterval(g_update_id);
        });
 
    $('[id^=connect-button]').on('click', function(){
        $('[id^=connect-button]').toggleClass('connect')
        if ($('[id^=connect-button]').hasClass('connect'))
        {
        $('[id^=kill-button]').on('click', kill_button);
        $('[id^=connect-button] .text').html('CONNECT');
        $(".empty").removeClass('empty');
        $(".field").empty();
        $(".bar").css("background",'white');
        clearInterval(s_update_id);
        clearInterval(g_update_id);
        clearInterval(vs_update_id);
        $.get("/command/quit");
        }
        else
        {
        $('[id^=connect-button] .spin').addClass("spinner");
        $('[id^=connect-button] .text').addClass("hidden");
        $.getJSON('ajax/parameters').done(set)
        .fail(function(jqxhr){
            alert("WARNING!\n\nUnable to connect to HPe-RC.");
            $('[id^=connect-button]').toggleClass('connect');
            })
        .done(function(){
        $('[id^=kill-button]').off('click');
        $('[id^=connect-button] .text').html('DISCONNECT');
        $.get("/start/monitor");
        })
        .always(function(){
        $('[id^=connect-button] .spin').removeClass("spinner");
        $('[id^=connect-button] .text').removeClass("hidden");
        })
         
        } 
        });

       
});
