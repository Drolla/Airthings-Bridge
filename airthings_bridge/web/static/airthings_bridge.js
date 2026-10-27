/*************************************************************************
* Airthings Bridge
**************************************************************************
* airthings_bridge.js - Web UI
*
* The table of the current values and the graphs are built from the
* measurement and device metadata (/meta).
*
* Copyright (C) 2020-2026 Andreas Drollinger
*************************************************************************/

var DisplayType="Classic";

function Ajax(Method,Url,Body,Callback) {
	var xHttp = new XMLHttpRequest();
	xHttp.onreadystatechange = function() {
		if (xHttp.readyState==4 && xHttp.status==200)
			Callback(xHttp.responseText);
	}
	xHttp.open(Method,Url,true);
	xHttp.send(Body==""?null:Body);
}

function AjaxJsonGet(Url,Callback) {
	Ajax("GET",Url,"",function(responseText) {
		Callback(JSON.parse(responseText));
	});
}

function EscapeHtml(Text) {
	return String(Text).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function MeasurementTitle(Measurement) {
	return Measurement.label + (Measurement.unit ? " ["+Measurement.unit+"]" : "");
}

function LoadTable(Meta,DivId) {
	AjaxJsonGet("/data",function(JsonData) {
		var jsonURL = window.location.origin+"/data";
		var currentTime = JsonData["current_time"];
		var devices = JsonData["devices"];

		// Rows: the known measurements in their order, then the other values
		var rows = [];
		var titles = {};
		Meta.measurements.forEach(function (measurement) {
			rows.push(measurement.key);
			titles[measurement.key] = MeasurementTitle(measurement);
		});
		for (var deviceName in devices) {
			for (var key in devices[deviceName]) {
				if (!rows.includes(key)) rows.push(key);
			}
		}
		rows = rows.filter(function (key) {
			return Object.values(devices).some(function (values) { return key in values; });
		});

		var innerHTML = "<table><thead><tr><td></td>";
		for (var deviceName in devices) {
			innerHTML += "<th>"+EscapeHtml(deviceName)+"</th>";
		}
		innerHTML += "</tr><tr></tr></thead><tbody>";
		rows.forEach(function (key) {
			innerHTML += "<tr><td>"+EscapeHtml(key=="update_time" ? "Updated" : titles[key] || key)+"</td>";
			for (var deviceName in devices) {
				var values = devices[deviceName];
				if (!(key in values)) {
					innerHTML += "<td></td>";
				} else if (key=="update_time") {
					innerHTML += "<td>"+(currentTime-values[key])+"s ago</td>";
				} else {
					innerHTML += "<td>"+EscapeHtml(values[key])+"</td>";
				}
			}
			innerHTML += "</tr>";
		});
		innerHTML += "</tbody></table>";
		innerHTML += "<br>Data in JSON format: <a href=\""+jsonURL+"\">"+jsonURL+"</a>";
		document.getElementById(DivId).innerHTML = innerHTML;
	});
}

function LoadGraphs(Meta,DivId) {
	// One graph per measurement that is logged by at least one device
	var graphList = Meta.measurements.filter(function (measurement) {
		return Meta.devices.some(function (device) {
			return device.logged.includes(measurement.key);
		});
	});

	var innerHTML = "";
	graphList.forEach(function (measurement) {
		var id = "graph_"+measurement.key;
		innerHTML += '<div id="'+id+'" class="graph_container">' +
		               '<div id="'+id+'_label" class="graph_label"></div>' +
		               '<div id="'+id+'_graph" class="graph_div"></div>' +
		             '</div>';
	});
	document.getElementById(DivId).innerHTML = innerHTML;

	var gs = [];
	var currentTime = Date.now();

	function LoadGraphsNextGraph() {
		if (graphList.length==0) {
			if (gs.length>1) {
				Dygraph.synchronize(gs, {
					selection: false,
					zoom: true,
					range: false
				});
			}
			return;
		}
		var measurement = graphList.shift();
		var id = "graph_"+measurement.key;
		gs.push(new Dygraph(
			document.getElementById(id+'_graph'),
			"/csv?*:"+measurement.key, {
				title: measurement.label,
				labelsSeparateLines: true,
				labelsDiv: document.getElementById(id+'_label'),
				ylabel: measurement.unit,
				showRangeSelector: gs.length%2==0,
				rangeSelectorHeight: (DisplayType=="Mobile" ? 60 : 30),
				rangeSelectorPlotLineWidth : 3,
				strokeWidth: (DisplayType=="Mobile" ? 4 : 2),
				axisLabelFontSize: (DisplayType=="Mobile" ? 24 : 14),
				dateWindow: [currentTime-24*3600*1000, currentTime],
			}
		));
		gs[gs.length-1].ready(LoadGraphsNextGraph);
	};
	LoadGraphsNextGraph();
}

function LoadPage(TableDivId,GraphsDivId) {
	AjaxJsonGet("/meta",function(Meta) {
		LoadTable(Meta,TableDivId);
		setInterval(function () { LoadTable(Meta,TableDivId); },60000);
		setTimeout(function () { LoadGraphs(Meta,GraphsDivId); },1000);
	});
}
