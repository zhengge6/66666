var e = require("@babel/runtime/helpers/slicedToArray"), t = n(require("@utils/util")), o = (n(require("@utils/http")), 
n(require("@utils/log")));

function n(e) {
    return e && e.__esModule ? e : {
        default: e
    };
}

App({
    onLaunch: function(e) {
        o.default.info("App 启动参数", e, t.default.info, t.default.device), this.autoUpdate(), 
        this.setCaptureListener(), this.loadFonts(), this.loadSDK();
    },
    autoUpdate: function() {
        var e = wx.getUpdateManager();
        e.onCheckForUpdate(function(t) {
            t.hasUpdate && (e.onUpdateReady(function() {
                e.applyUpdate();
            }), e.onUpdateFailed(function() {
                wx.showModal({
                    title: "已经有新版本了哟~",
                    content: "请您重新打开当前小程序哟~",
                    showCancel: !1
                });
            }));
        });
    },
    setCaptureListener: function() {
        wx.onUserCaptureScreen(function() {
            return {
                query: "from=capture",
                promise: new Promise(function(n) {
                    var a = getCurrentPages(), u = a[a.length - 1], i = u.options.map(function(t) {
                        var o = e(t, 2), n = o[0], a = o[1];
                        return "".concat(n, "=").concat(a);
                    }).join("&");
                    o.default.info("用户截屏", {
                        route: u.route,
                        query: i
                    }), t.default.showInfo("您已截屏\n请注意隐私安全"), n({
                        query: "".concat(i, "&from=capture")
                    });
                })
            };
        }), wx.onScreenRecordingStateChanged(function(e) {
            "start" == e.state && t.default.showInfo("您正在录屏\n请注意隐私安全", "none", !1, 6), "stop" == e.state && t.default.showInfo("录屏完成\n请注意隐私安全");
        });
    },
    onPageNotFound: function() {
        wx.redirectTo({
            url: "/pages/home/home"
        });
    },
    loadFonts: function() {
        wx.loadFontFace({
            global: !0,
            family: "SourceHan",
            source: 'url("https://cdn.micono.eu.org/fonts/思源黑体.woff2")',
            scopes: [ "webview", "native" ]
        }), wx.loadFontFace({
            global: !0,
            family: "DingTalk-JinBuTi",
            source: 'url("https://cdn.micono.eu.org/fonts/钉钉进步体.woff")',
            scopes: [ "webview", "native" ]
        }), wx.loadFontFace({
            global: !0,
            family: "DeYiHei",
            source: 'url("https://cdn.micono.eu.org/fonts/得意黑.ttf")',
            scopes: [ "webview", "native" ]
        });
    },
    loadSDK: function() {
        if ("devtools" != t.default.device.platform) require("@utils/sdk/mtj-wx-sdk");
    }
});