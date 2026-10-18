package com.oitnetportal

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import com.oitnetportal.core.UnavailablePortalCoreBridge
import com.oitnetportal.ui.PortalApp
import com.oitnetportal.ui.PortalViewModel

class MainActivity : ComponentActivity() {
    private val portalViewModel: PortalViewModel by viewModels {
        PortalViewModel.factory(UnavailablePortalCoreBridge())
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            PortalApp(portalViewModel)
        }
    }
}
